"""Bounded, cited chat over already-published Vigie data."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

import requests
from databricks.sdk.core import Config

from answer_check import unsupported_figures
from chat_intents import asks_for_explanation, question_intent

DEFAULT_MODEL = "databricks-gpt-oss-20b"
SYSTEM = """You are Vigie, a French financial-information assistant. Answer only from CONTEXT.
Never invent values, dates, or sources; do not provide investment advice. Keep the answer under 160 French words. Return strict JSON:
{"answer":"...","citations":[{"label":"...","url":"..."}],"used_kpis":[{"company_id":"...","metric_id":"...","period_id":"..."}],"caveat":"... or null"}.
Citations must use only URLs from CONTEXT. Cite at least one URL for factual answers."""


def _json_default(value: Any) -> Any:
    """Convert scalar and array values returned by the SQL/Pandas layer."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported context value: {type(value).__name__}")


def compact_context(
    comparisons: list[dict[str, Any]], news: list[dict[str, Any]], documents: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Keep only published fields useful to a chat answer and fit a bounded prompt."""
    comparison_fields = ("company_id", "metric_id", "current_period_id", "current_value", "previous_period_id", "previous_value", "change_pct")
    document_fields = ("company_id", "reporting_period", "source_url", "fetched_at")
    return {
        "comparisons": [{field: row.get(field) for field in comparison_fields if row.get(field) is not None} for row in comparisons[:80]],
        "news": [
            {
                "company_ids": row.get("relevant_company_ids"),
                "title": row.get("title"),
                "published_at": row.get("published_at"),
                "summary": (row.get("summary") or "")[:360],
                "source_url": row.get("source_url"),
            }
            for row in news[:8]
        ],
        "documents": [{field: row.get(field) for field in document_fields if row.get(field) is not None} for row in documents[:4]],
    }


PERCENT_METRICS = {"licat_ratio", "solvency_ratio", "core_roe"}
DETERMINISTIC_CAVEAT = "Réponse déterministe fondée sur les valeurs publiées; ce n’est pas un conseil financier."


def _prior_year(period: str | None) -> str | None:
    match = re.fullmatch(r"(20\d{2})-Q([1-4])", str(period or ""))
    return f"{int(match.group(1)) - 1}-Q{match.group(2)}" if match else None


def _citations_and_used(rows: list[dict[str, Any]], metric_id: str, context: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    urls = {document.get("company_id"): document.get("source_url") for document in context.get("documents", [])}
    citations = [{"label": f"Rapport officiel {row['company_id']}", "url": urls[row["company_id"]]} for row in rows if urls.get(row["company_id"])]
    used = [{"company_id": row["company_id"], "metric_id": metric_id, "period_id": row.get("current_period_id")} for row in rows]
    return citations[:4], used


def _variation_answer(rows: list[dict[str, Any]], metric_id: str, label: str, context: dict[str, Any]) -> dict[str, Any]:
    """Year-over-year change, only against the same quarter of the prior year."""
    lines = []
    for row in rows:
        current, previous = row.get("current_value"), row.get("previous_value")
        legitimate = previous is not None and current is not None and row.get("previous_period_id") == _prior_year(row.get("current_period_id"))
        if not legitimate:
            lines.append(f"{row['company_id']} : variation annuelle N/A (le même trimestre de l’année précédente n’est pas disponible)")
        elif metric_id in PERCENT_METRICS:
            lines.append(f"{row['company_id']} : {current} vs {previous} en {row['previous_period_id']} ({float(current) - float(previous):+.1f} pp)")
        elif float(previous) == 0:
            lines.append(f"{row['company_id']} : variation annuelle N/A (valeur antérieure nulle)")
        else:
            lines.append(f"{row['company_id']} : {current} vs {previous} en {row['previous_period_id']} ({(float(current) - float(previous)) / float(previous) * 100:+.1f} %)")
    citations, used = _citations_and_used(rows, metric_id, context)
    return {"answer": f"Variation annuelle — {label.capitalize()} : " + "; ".join(lines) + ".", "citations": citations, "used_kpis": used, "caveat": DETERMINISTIC_CAVEAT}


def _ranking_answer(rows: list[dict[str, Any]], metric_id: str, label: str, context: dict[str, Any]) -> dict[str, Any]:
    """Companies ordered from the highest to the lowest published value."""
    ordered = sorted((row for row in rows if row.get("current_value") is not None), key=lambda row: float(row["current_value"]), reverse=True)
    values = "; ".join(f"{row['company_id']} : {row.get('current_value')} ({row.get('current_period_id')})" for row in ordered)
    citations, used = _citations_and_used(ordered, metric_id, context)
    return {"answer": f"{label.capitalize()}, du plus élevé au moins élevé — {values}.", "citations": citations, "used_kpis": used, "caveat": DETERMINISTIC_CAVEAT}


def deterministic_answer(question: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Answer simple KPI lookups locally, retaining the same citation guardrail."""
    normalized = unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode().lower()
    if asks_for_explanation(normalized):
        return None
    metric_aliases = {
        "core_eps": ("bpa", "eps", "benefice par action"),
        "core_earnings": ("benefice de base", "benefices de base", "core earnings", "resultat des activites de base", "benefices des 4"),
        "net_income": ("resultat net", "net income", "benefice net"),
        "licat_ratio": ("licat", "solvabilite"),
        "core_roe": ("roe", "rendement des capitaux propres"),
        "assets_under_management": ("actifs sous gestion", "assets under management", "aum"),
        "assets_under_administration": ("actifs sous administration", "assets under administration", "aua"),
        "total_client_assets": ("actifs clients", "total client assets"),
    }
    metric_id = next((metric for metric, aliases in metric_aliases.items() if any(alias in normalized for alias in aliases)), None)
    if not metric_id:
        return None
    period_match = re.search(r"(?:20\d{2}\s*[- ]?\s*[qt][1-4]|[qt][1-4]\s*20\d{2})", normalized)
    requested_period = None
    if period_match:
        digits = re.findall(r"20\d{2}|[qt][1-4]", period_match.group())
        year = digits[0] if digits[0].startswith("20") else digits[1]
        quarter = digits[1] if digits[0].startswith("20") else digits[0]
        requested_period = f"{year}-Q{quarter[-1]}"
    company_aliases = {
        "MFC": ("mfc", "manuvie", "manulife"), "SLF": ("slf", "sun life"),
        "GWO": ("gwo", "great-west", "great west", "canada life"),
        "IAG": ("iag", "ia groupe", "ia financial", "industrielle alliance", " de ia", " de l'ia"),
    }
    requested_companies = {
        company for company, aliases in company_aliases.items() if any(alias in normalized for alias in aliases)
    }
    rows = [
        row for row in context.get("comparisons", [])
        if row.get("metric_id") == metric_id
        and (not requested_period or row.get("current_period_id") == requested_period)
        and (not requested_companies or row.get("company_id") in requested_companies)
    ]
    if not rows:
        return {"answer": "Aucune valeur publiée ne correspond à cette période et à cet indicateur.", "citations": [], "caveat": "Les périodes disponibles diffèrent selon l’assureur."}
    labels = {"core_eps": "BPA de base", "core_earnings": "résultat des activités de base", "net_income": "résultat net", "licat_ratio": "ratio de solvabilité", "core_roe": "ROE de base", "assets_under_management": "actifs sous gestion", "assets_under_administration": "actifs sous administration", "total_client_assets": "actifs clients totaux"}
    intent = question_intent(normalized)
    if intent == "variation":
        return _variation_answer(rows, metric_id, labels[metric_id], context)
    if intent == "ranking" and len(rows) > 1:
        return _ranking_answer(rows, metric_id, labels[metric_id], context)
    values = "; ".join(f"{row['company_id']} : {row.get('current_value')} ({row.get('current_period_id')})" for row in rows)
    urls = {document.get("company_id"): document.get("source_url") for document in context.get("documents", [])}
    citations = [{"label": f"Rapport officiel {row['company_id']}", "url": urls[row["company_id"]]} for row in rows if urls.get(row["company_id"])]
    used = [{"company_id": row["company_id"], "metric_id": metric_id, "period_id": row.get("current_period_id")} for row in rows]
    return {"answer": f"{labels[metric_id].capitalize()} — {values}.", "citations": citations[:4], "used_kpis": used, "caveat": "Réponse déterministe fondée sur les valeurs publiées; ce n’est pas un conseil financier."}


def fallback_answer(context: dict[str, Any]) -> dict[str, Any]:
    """Return a useful, non-generative answer if model serving is unavailable."""
    rows = [row for row in context.get("comparisons", []) if row.get("metric_id") == "core_earnings"]
    if not rows:
        return {"answer": "Le modèle est temporairement indisponible et aucune valeur de base n'est publiée.", "citations": [], "used_kpis": [], "caveat": "Réessayez plus tard."}
    values = "; ".join(f"{row['company_id']} : {row.get('current_value')} ({row.get('current_period_id')})" for row in rows)
    urls = {document.get("company_id"): document.get("source_url") for document in context.get("documents", [])}
    citations = [{"label": f"Rapport officiel {row['company_id']}", "url": urls[row["company_id"]]} for row in rows if urls.get(row["company_id"])]
    used = [{"company_id": row["company_id"], "metric_id": "core_earnings", "period_id": row.get("current_period_id")} for row in rows]
    return {"answer": f"Le modèle est temporairement indisponible. Derniers résultats de base publiés — {values}.", "citations": citations, "used_kpis": used, "caveat": "Réponse de secours déterministe; ce n’est pas un conseil financier."}


def _response_text(content: Any) -> str:
    if isinstance(content, str) and content.lstrip().startswith("["):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            pass
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
    if isinstance(content, str):
        return content
    raise ValueError("Model response is not text.")


def _response_object(content: Any) -> dict[str, Any]:
    text = _response_text(content).strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise ValueError("Réponse du modèle non conforme.")
        parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        raise ValueError("Réponse du modèle non conforme.")
    return parsed


def ask(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, str]],
    *,
    system: str = SYSTEM,
    allowed_kpis: set[tuple[Any, Any, Any]] | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if not 3 <= len(question.strip()) <= 600:
        raise ValueError("La question doit contenir entre 3 et 600 caractères.")
    config = Config()
    context_json = json.dumps(context, ensure_ascii=False, default=_json_default)
    messages = [{"role": "system", "content": system + "\nCONTEXT:\n" + context_json}]
    messages.extend({"role": item["role"], "content": item["content"][:1200]} for item in history[-6:])
    messages.append({"role": "user", "content": question.strip()})
    payload = {"messages": messages, "temperature": 0.1, "max_tokens": 1536}
    if reasoning_effort:
        # A reasoning model can spend the whole token budget thinking and never answer; "low" keeps it bounded.
        payload["reasoning_effort"] = reasoning_effort
    response = requests.post(
        f"{config.host.rstrip('/')}/serving-endpoints/{os.environ.get('VIGIE_CHAT_ENDPOINT', DEFAULT_MODEL)}/invocations",
        headers={**config.authenticate(), "Content-Type": "application/json"},
        json=payload, timeout=45,
    )
    response.raise_for_status()
    parsed = _response_object(response.json()["choices"][0]["message"]["content"])
    allowed = {item.get("source_url") for item in context.get("news", [])} | {item.get("source_url") for item in context.get("documents", [])}
    citations = {}
    for item in parsed.get("citations") or []:
        if isinstance(item, dict) and item.get("url") in allowed:
            citations.setdefault(item["url"], item)
    parsed["citations"] = list(citations.values())[:6]
    if allowed_kpis is None:
        allowed_kpis = {
            (row.get("company_id"), row.get("metric_id"), row.get("current_period_id"))
            for row in context.get("comparisons", [])
        }
    parsed["used_kpis"] = [
        item for item in parsed.get("used_kpis") or []
        if isinstance(item, dict)
        and (item.get("company_id"), item.get("metric_id"), item.get("period_id")) in allowed_kpis
    ][:12]
    unverified = unsupported_figures(parsed.get("answer", ""), context)
    if unverified:
        # Not a proof of an error (a rounded or derived figure may escape the check), so it is shown, not blocked.
        parsed["unverified_figures"] = unverified
        notice = "Vérification : ces chiffres n’ont pas été retrouvés dans les données publiées : " + ", ".join(unverified) + ". Vérifiez-les avant usage."
        parsed["caveat"] = f"{parsed['caveat']} {notice}" if parsed.get("caveat") else notice
    return parsed
