"""Bounded, cited chat over the already-published P&C observations.

Same guardrails as the life chat (answers only from a bounded context, citations restricted to URLs
present in that context, KPIs checked against the published rows), with P&C-specific rules: closing
dates and calendar bases differ between issuers, `N/A` means no validated value, and a year-over-year
change is only legitimate for the same quarter and the same calendar basis. The context holds P&C data
only, so the two universes stay isolated.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from chat_intents import asks_for_explanation, question_intent
from pnc_yoy import pnc_yoy, prior_year_period, prior_year_row
from shared_ui import format_value

PNC_SYSTEM = """You are Vigie, a French financial-information assistant for four Canadian P&C insurers: IFC (Intact Financial, consolidated), AV (Aviva Canada, Canada segment), TD (TD Insurance, segment) and DFY (Definity Financial, consolidated). Answer only from CONTEXT.
Never invent values, dates, or sources; do not provide investment advice. Keep the answer under 160 French words.
Rules: a lower combined, claims or expense ratio is more favourable. Issuers have different closing dates and calendar bases (fiscal or calendar): mention the closing date and basis when comparing issuers, and never state a year-over-year change unless CONTEXT holds the same quarter of the prior year with the same calendar basis. N/A means no validated value was published, not that the issuer did not report: use NOTES to explain known gaps. Operating net income is a non-IFRS measure specific to each insurer. When comparing values, quote the numbers and check which one is higher before saying so; do not invent averages or trends that CONTEXT does not hold.
Return strict JSON:
{"answer":"...","citations":[{"label":"...","url":"..."}],"used_kpis":[{"company_id":"...","metric_id":"...","period_id":"..."}],"caveat":"... or null"}.
Citations must use only URLs from CONTEXT: cite the URL that supports the answer when one exists, otherwise return an empty list."""

NOTES = (
    "Aviva Canada publie des résultats semestriels: aucun ratio combiné trimestriel canadien isolé hors T1 n'est validé; il reste N/A.",
    "TD Insurance: le rapport de TD présente un segment combiné Gestion de patrimoine et Assurance; seuls les indicateurs d'assurance validés sont publiés.",
    "Intact et Definity sont consolidés; Aviva Canada et TD Insurance sont des segments: périmètres non comparables.",
    "Les trimestres de TD sont fiscaux (le T2 se termine le 30 avril); ceux des autres assureurs suivent le calendrier civil.",
    "Le résultat net opérationnel est une mesure non-IFRS propre à chaque assureur.",
)
LABELS = {
    "combined_ratio": "Ratio combiné", "claims_ratio": "Ratio de sinistres", "expense_ratio": "Ratio de frais",
    "insurance_revenue": "Produits d'assurance", "operating_income": "Résultat net opérationnel", "net_income": "Résultat net",
}
RATIOS = {"combined_ratio", "claims_ratio", "expense_ratio"}
# Order matters: the operating measure must be tested before the plain net income.
METRIC_ALIASES = (
    ("operating_income", ("resultat net operationnel", "operating net income", "operating income", "resultat operationnel")),
    ("combined_ratio", ("ratio combine", "combined ratio", "cor")),
    ("claims_ratio", ("ratio de sinistres", "ratio des sinistres", "claims ratio", "loss ratio")),
    ("expense_ratio", ("ratio de frais", "ratio des frais", "expense ratio")),
    ("insurance_revenue", ("produits d assurance", "revenus d assurance", "insurance revenue")),
    ("net_income", ("resultat net", "net income", "benefice net")),
)
COMPANY_ALIASES = {
    "IFC": ("intact", "ifc"), "AV": ("aviva", "av"), "TD": ("td insurance", "td"), "DFY": ("definity", "dfy"),
}
COMPANY_NAMES = {"IFC": "Intact Financial", "AV": "Aviva Canada", "TD": "TD Insurance", "DFY": "Definity Financial"}
QUARTER = re.compile(r"20\d{2}-Q[1-4]")
OBSERVATION_FIELDS = ("company_id", "metric_id", "period_id", "value", "unit", "period_end", "calendar_basis", "disclosure_scope")


def compact_pnc_context(rows: Iterable[Mapping[str, Any]], news: Iterable[Mapping[str, Any]], max_periods: int = 6) -> dict[str, Any]:
    """Keep the last quarters of published observations, the newest newsroom items and the known gaps."""
    rows = [row for row in rows if QUARTER.fullmatch(str(row.get("period_id", "")))]
    periods = sorted({row["period_id"] for row in rows}, reverse=True)[:max_periods]
    observations = sorted((row for row in rows if row["period_id"] in periods), key=lambda row: (str(row["company_id"]), str(row["metric_id"])))
    observations.sort(key=lambda row: row["period_id"], reverse=True)  # newest quarter first; the sort is stable
    observations = observations[:160]
    documents, seen = [], set()
    for row in observations:
        key = (row["company_id"], row["period_id"], row.get("source_url"))
        if row.get("source_url") and key not in seen:
            seen.add(key)
            documents.append({"company_id": row["company_id"], "period_id": row["period_id"], "source_url": row["source_url"]})
    return {
        "observations": [{field: row.get(field) for field in OBSERVATION_FIELDS if row.get(field) is not None} for row in observations],
        "news": [
            {"company_ids": [item.get("company_id")], "title": item.get("title"), "published_at": item.get("published_at"),
             "summary": (item.get("summary") or "")[:360], "source_url": item.get("source_url")}
            for item in list(news)[:8]
        ],
        "documents": documents[:40],
        "notes": list(NOTES),
    }


def allowed_kpis(context: Mapping[str, Any]) -> set[tuple[Any, Any, Any]]:
    return {(row.get("company_id"), row.get("metric_id"), row.get("period_id")) for row in context.get("observations", [])}


def _normalize(text: str) -> str:
    text = text.replace("’", " ").replace("'", " ")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _mentions(normalized: str, alias: str) -> bool:
    # every word may carry a plural 's' ("ratios combinés", "résultats nets")
    pattern = r"\s+".join(f"{re.escape(word)}s?" for word in alias.split())
    return re.search(rf"\b{pattern}\b", normalized) is not None


def _report_urls(context: Mapping[str, Any], period: str | None) -> dict[str, str]:
    """The official report URL per issuer for one quarter, from the context's documents."""
    urls: dict[str, str] = {}
    for document in context.get("documents", []):
        if document.get("period_id") == period and document.get("source_url"):
            urls.setdefault(document["company_id"], document["source_url"])
    return urls


def _basis(row: Mapping[str, Any]) -> str:
    return "fiscal" if row.get("calendar_basis") == "fiscal" else "civil"


AVIVA_HY26_URL = "https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/"
GAP_QUESTION = re.compile(r"n/a|pourquoi|lacune|absent|manque|pas de valeur|aucune valeur")


def _gap_answer(normalized: str, context: Mapping[str, Any]) -> dict[str, Any] | None:
    """Explain a known structural gap (Aviva, TD) straight from the notes, without the model."""
    if not GAP_QUESTION.search(normalized):
        return None
    notes = list(context.get("notes", []))
    if _mentions(normalized, "aviva") and notes:
        return {"answer": notes[0], "citations": [{"label": "Communiqué semestriel d'Aviva Canada", "url": AVIVA_HY26_URL}],
                "caveat": "N/A signifie qu'aucune valeur validée n'est publiée pour ce trimestre, pas qu'Aviva n'a rien communiqué."}
    if (_mentions(normalized, "td insurance") or _mentions(normalized, "td")) and len(notes) > 1:
        td_documents = sorted((doc for doc in context.get("documents", []) if doc.get("company_id") == "TD"), key=lambda doc: doc["period_id"], reverse=True)
        citations = [{"label": "Rapport officiel TD", "url": td_documents[0]["source_url"]}] if td_documents else []
        return {"answer": notes[1], "citations": citations,
                "caveat": "Seuls les indicateurs d'assurance validés sont publiés; les autres restent N/A."}
    return None


def _citations(companies: list[str], selected: Mapping[str, Mapping[str, Any]], context: Mapping[str, Any], period: str) -> list[dict[str, str]]:
    urls = _report_urls(context, period)
    return [{"label": f"Rapport officiel {company}", "url": urls[company]} for company in companies if company in selected and urls.get(company)][:4]


def _variation_answer(metric_id: str, period: str, companies: list[str], selected: Mapping[str, Mapping[str, Any]], context: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Year-over-year change per issuer, with the same guardrails as the page (same quarter, same calendar basis)."""
    observations = context.get("observations", [])
    lines = []
    for company in companies:
        row = selected.get(company)
        if row is None:
            lines.append(f"{company} : N/A (aucune valeur validée)")
            continue
        yoy = pnc_yoy(row, observations)
        prior = prior_year_row(row, observations)
        if yoy is None or prior is None:
            lines.append(f"{company} : variation annuelle N/A (le même trimestre de l’année précédente n’est pas disponible avec la même base de calendrier)")
        else:
            text, symbol, prior_period = yoy
            lines.append(f"{company} : {format_value(row.get('value'), kind)} vs {format_value(prior.get('value'), kind)} en {prior_period} ({symbol} {text})")
    used = [{"company_id": company, "metric_id": metric_id, "period_id": period} for company in companies if company in selected]
    return {"answer": f"Variation annuelle — {LABELS[metric_id]} {period} : " + "; ".join(lines) + ".",
            "citations": _citations(companies, selected, context, period), "used_kpis": used,
            "caveat": "Variation calculée seulement contre le même trimestre de l’année précédente et la même base de calendrier; neutre quant à ce qui est favorable. Ce n’est pas un conseil financier."}


def _ranking_answer(metric_id: str, period: str, companies: list[str], selected: Mapping[str, Mapping[str, Any]], context: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Issuers ordered by published value; for a ratio the lowest comes first because it is the most favourable."""
    ratio = metric_id in RATIOS
    present = sorted((company for company in companies if company in selected), key=lambda company: float(selected[company]["value"]), reverse=not ratio)
    parts = [f"{company} : {format_value(selected[company].get('value'), kind)} (clôture {selected[company].get('period_end')}, {_basis(selected[company])})" for company in present]
    parts += [f"{company} : N/A (aucune valeur validée)" for company in companies if company not in selected]
    order = "du plus favorable (le plus bas) au moins favorable" if ratio else "du plus élevé au plus bas"
    used = [{"company_id": company, "metric_id": metric_id, "period_id": period} for company in present]
    return {"answer": f"{LABELS[metric_id]} {period}, {order} — " + "; ".join(parts) + ".",
            "citations": _citations(companies, selected, context, period), "used_kpis": used,
            "caveat": "Clôtures, calendriers et périmètres différents selon l’assureur; ce classement n’est pas un conseil financier."}


def deterministic_answer(question: str, context: Mapping[str, Any]) -> dict[str, Any] | None:
    """Answer a plain published-value lookup locally, keeping the citation guardrail."""
    normalized = _normalize(question)
    gap = _gap_answer(normalized, context)
    if gap:
        return gap
    if asks_for_explanation(normalized):
        return None
    metric_id = next((metric for metric, aliases in METRIC_ALIASES if any(_mentions(normalized, alias) for alias in aliases)), None)
    if not metric_id:
        return None
    observations = [row for row in context.get("observations", []) if row.get("metric_id") == metric_id]
    period_match = re.search(r"(20\d{2})\s*[- ]?\s*[qt]([1-4])|[qt]([1-4])\s*[- ]?\s*(20\d{2})", normalized)
    if period_match:
        year = period_match.group(1) or period_match.group(4)
        quarter = period_match.group(2) or period_match.group(3)
        period = f"{year}-Q{quarter}"
    else:
        period = max((row["period_id"] for row in observations), default=None)
    companies = [company for company, aliases in COMPANY_ALIASES.items() if any(_mentions(normalized, alias) for alias in aliases)]
    companies = companies or list(COMPANY_NAMES)
    selected = {row["company_id"]: row for row in observations if row.get("period_id") == period}
    if not period or not any(company in selected for company in companies):
        return {"answer": "Aucune valeur publiée ne correspond à cette période, à cet indicateur et à ces assureurs.", "citations": [],
                "caveat": "N/A signifie qu'aucune valeur validée n'est publiée pour ce trimestre."}
    kind = "billion" if next(iter(selected.values())).get("unit") == "CAD_BILLION" else "percent"
    intent = question_intent(normalized)
    if intent == "variation":
        return _variation_answer(metric_id, period, companies, selected, context, kind)
    if intent == "ranking" and sum(company in selected for company in companies) > 1:
        return _ranking_answer(metric_id, period, companies, selected, context, kind)
    parts = []
    for company in companies:
        row = selected.get(company)
        if row:
            parts.append(f"{company} : {format_value(row.get('value'), kind)} (clôture {row.get('period_end')}, {_basis(row)})")
        else:
            parts.append(f"{company} : N/A (aucune valeur validée)")
    urls = _report_urls(context, period)
    citations = [{"label": f"Rapport officiel {company}", "url": urls[company]} for company in companies if company in selected and urls.get(company)]
    used = [{"company_id": company, "metric_id": metric_id, "period_id": period} for company in companies if company in selected]
    caveat = "Réponse déterministe fondée sur les valeurs publiées; clôtures et périmètres différents selon l'assureur; ce n'est pas un conseil financier."
    if metric_id in RATIOS and len(used) > 1:
        caveat = "Un ratio plus bas est plus favorable. " + caveat
    return {"answer": f"{LABELS[metric_id]} {period} — " + "; ".join(parts) + ".", "citations": citations[:4], "used_kpis": used, "caveat": caveat}


def fallback_answer(context: Mapping[str, Any]) -> dict[str, Any]:
    """A useful, non-generative answer when model serving is unavailable."""
    rows = [row for row in context.get("observations", []) if row.get("metric_id") == "combined_ratio"]
    latest = max((row["period_id"] for row in rows), default=None)
    rows = [row for row in rows if row["period_id"] == latest]
    if not rows:
        return {"answer": "Le modèle est temporairement indisponible et aucun ratio combiné n'est publié.", "citations": [], "used_kpis": [], "caveat": "Réessayez plus tard."}
    values = "; ".join(f"{row['company_id']} : {format_value(row.get('value'), 'percent')} (clôture {row.get('period_end')}, {_basis(row)})" for row in rows)
    urls = _report_urls(context, latest)
    citations = [{"label": f"Rapport officiel {row['company_id']}", "url": urls[row["company_id"]]} for row in rows if urls.get(row["company_id"])]
    used = [{"company_id": row["company_id"], "metric_id": "combined_ratio", "period_id": latest} for row in rows]
    return {"answer": f"Le modèle est temporairement indisponible. Derniers ratios combinés publiés ({latest}) — {values}.", "citations": citations[:4],
            "used_kpis": used, "caveat": "Réponse de secours déterministe; ce n'est pas un conseil financier."}
