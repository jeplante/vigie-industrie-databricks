"""Bounded, cited chat over already-published Vigie data."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

import requests
from databricks.sdk.core import Config

DEFAULT_MODEL = "databricks-gpt-oss-20b"
SYSTEM = """You are Vigie, a French financial-information assistant. Answer only from CONTEXT.
Never invent values, dates, or sources; do not provide investment advice. Keep the answer under 160 French words. Return strict JSON:
{"answer":"...","citations":[{"label":"...","url":"..."}],"caveat":"... or null"}.
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


def deterministic_answer(question: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Answer simple KPI lookups locally, retaining the same citation guardrail."""
    normalized = unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode().lower()
    metric_aliases = {
        "core_eps": ("bpa", "eps", "benefice par action"),
        "core_earnings": ("benefice de base", "benefices de base", "core earnings", "resultat des activites de base", "benefices des 4"),
        "net_income": ("resultat net", "net income", "benefice net"),
        "licat_ratio": ("licat", "solvabilite"),
        "core_roe": ("roe", "rendement des capitaux propres"),
    }
    metric_id = next((metric for metric, aliases in metric_aliases.items() if any(alias in normalized for alias in aliases)), None)
    if not metric_id:
        return None
    period_match = re.search(r"(?:20\d{2}\s*[- ]?\s*q[1-4]|q[1-4]\s*20\d{2})", normalized)
    requested_period = None
    if period_match:
        digits = re.findall(r"20\d{2}|q[1-4]", period_match.group())
        requested_period = f"{digits[0]}-{digits[1].upper()}" if digits[0].startswith("20") else f"{digits[1]}-{digits[0].upper()}"
    rows = [row for row in context.get("comparisons", []) if row.get("metric_id") == metric_id and (not requested_period or row.get("current_period_id") == requested_period)]
    if not rows:
        return {"answer": "Aucune valeur publiée ne correspond à cette période et à cet indicateur.", "citations": [], "caveat": "Les périodes disponibles diffèrent selon l’assureur."}
    labels = {"core_eps": "BPA de base", "core_earnings": "résultat des activités de base", "net_income": "résultat net", "licat_ratio": "ratio de solvabilité", "core_roe": "ROE de base"}
    values = "; ".join(f"{row['company_id']} : {row.get('current_value')} ({row.get('current_period_id')})" for row in rows)
    urls = {document.get("company_id"): document.get("source_url") for document in context.get("documents", [])}
    citations = [{"label": f"Rapport officiel {row['company_id']}", "url": urls[row["company_id"]]} for row in rows if urls.get(row["company_id"])]
    return {"answer": f"{labels[metric_id].capitalize()} — {values}.", "citations": citations[:4], "caveat": "Réponse déterministe fondée sur les valeurs publiées; ce n’est pas un conseil financier."}


def ask(question: str, context: dict[str, Any], history: list[dict[str, str]]) -> dict[str, Any]:
    if not 3 <= len(question.strip()) <= 600:
        raise ValueError("La question doit contenir entre 3 et 600 caractères.")
    config = Config()
    context_json = json.dumps(context, ensure_ascii=False, default=_json_default)
    messages = [{"role": "system", "content": SYSTEM + "\nCONTEXT:\n" + context_json}]
    messages.extend({"role": item["role"], "content": item["content"][:1200]} for item in history[-6:])
    messages.append({"role": "user", "content": question.strip()})
    response = requests.post(
        f"{config.host.rstrip('/')}/serving-endpoints/{os.environ.get('VIGIE_CHAT_ENDPOINT', DEFAULT_MODEL)}/invocations",
        headers={**config.authenticate(), "Content-Type": "application/json"},
        json={"messages": messages, "temperature": 0.1, "max_tokens": 1536}, timeout=45,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if isinstance(content, str) and content.lstrip().startswith("["):
        structured_content = json.loads(content)
        if isinstance(structured_content, list):
            content = "".join(
                item.get("text", "")
                for item in structured_content
                if isinstance(item, dict) and item.get("type") == "text"
            )
    elif isinstance(content, list):
        content = "".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
    if not isinstance(content, str):
        raise ValueError("Model response is not text.")
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        raise ValueError("Réponse du modèle non conforme.")
    allowed = {item.get("source_url") for item in context.get("news", [])} | {item.get("source_url") for item in context.get("documents", [])}
    parsed["citations"] = [item for item in parsed.get("citations", []) if isinstance(item, dict) and item.get("url") in allowed][:6]
    return parsed
