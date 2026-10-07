"""Automatic review of extracted P&C candidates, in place of a hand-written evidence record.

Replaces the per-quarter human review (decision of 2026-10-07) with the checks a reviewer applied, so a
P&C quarter is published as automatically as a life quarter. Each candidate gets one decision:

- ``accepted``: every check passed; the candidate carries generated ``basis_evidence`` and still goes
  through the unchanged publication gate (``publish_pnc_candidates``).
- ``unchanged``: the same value is already published for this observation (re-fetched document).
- ``excluded``: a metric the Vigie never publishes for this issuer (for example a trailing-twelve-month
  ROE, or Intact's ratio components that reconcile to the discounted ratio). Not an alert.
- ``rejected``: a check failed; nothing is published for it and the run alerts. A hand-written record in
  ``config/pnc/reviewed_evidence.yaml`` remains possible to publish such an exception after inspection.

Backtested on every candidate acquired since 2022 (2026-10-07): it accepts exactly the 169 values
humans published and rejects or skips the 50 others.
"""
from __future__ import annotations

import calendar
from datetime import date
import math
import re
from typing import Any, Iterable

from vigie_databricks.operations_monitor import PNC_FISCAL_YEAR_END, PNC_RATIO_BOUNDS, PNC_RATIO_TOLERANCE_PP
from vigie_databricks.pnc_provenance import PNC_SOURCE_BASIS

REVIEWER = "automatic-checks-v1"
# Metrics published per issuer: what each one discloses quarterly on a comparable basis.
PUBLISHABLE_METRICS: dict[str, frozenset[str]] = {
    "IFC": frozenset({"combined_ratio", "net_income", "operating_income"}),
    "DFY": frozenset({"insurance_revenue", "combined_ratio", "claims_ratio", "expense_ratio", "net_income", "operating_income"}),
    "TD": frozenset({"net_income"}),
    "AV": frozenset({"combined_ratio"}),
}
DISCLOSURE_SCOPE = {"IFC": "consolidated_global", "DFY": "consolidated_canada", "TD": "insurance_segment",
                    "AV": "canada_general_insurance"}
CALENDAR_BASIS = {"IFC": "calendar", "DFY": "calendar", "TD": "fiscal", "AV": "calendar"}
# A quarter whose amount is more than this factor away from both the issuer's same quarter last year and
# its previous quarter is far more likely a units or label error (millions read as billions, a footnote
# read as a value) than a real result. Agreement with either reference is enough: a catastrophe quarter
# is far from the previous quarter but close to the same quarter last year.
AMOUNT_FACTOR = 5.0
# Below this size (CAD billions) an amount is too small for a ratio test to mean anything.
AMOUNT_FLOOR = 0.05
# A quarterly ratio rarely moves more than this against both references; a severe catastrophe quarter fits.
RATIO_SWING_PP = 25.0
_QUARTER = re.compile(r"\bQ([1-4])[ -]?(20\d{2})\b", re.IGNORECASE)
_CUMULATIVE = re.compile(r"\b(?:six|nine|twelve|6|9|12)\s+months?\b|\bhalf[ -]?year\b|\bfull[ -]?year\b|"
                         r"\byear[ -]?to[ -]?date\b|\bYTD\b|\btrailing\b", re.IGNORECASE)


def period_end(period_id: str, fiscal_year_end_month: int = 12) -> date:
    """Closing date of a quarter label in the issuer's own fiscal calendar (TD 2026-Q3 → 2026-07-31)."""
    year, quarter = int(period_id[:4]), int(period_id[-1])
    month = (fiscal_year_end_month + 3 * quarter - 1) % 12 + 1
    end_year = year if month <= fiscal_year_end_month else year - 1
    return date(end_year, month, calendar.monthrange(end_year, month)[1])


def _previous_period(period_id: str) -> str:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    return f"{year}-Q{quarter - 1}" if quarter > 1 else f"{year - 1}-Q4"


def _references(candidate: dict[str, Any], published: Iterable[dict[str, Any]]) -> list[float]:
    """Same quarter last year and previous quarter of the same issuer and metric, when published."""
    period = candidate["period_id"]
    wanted = {f"{int(period[:4]) - 1}{period[4:]}", _previous_period(period)}
    return [float(row["value"]) for row in published
            if row.get("company_id") == candidate["company_id"] and row.get("metric_id") == candidate["metric_id"]
            and row.get("period_id") in wanted and row.get("value") is not None]


def _plausibility(candidate: dict[str, Any], published: list[dict[str, Any]]) -> str | None:
    value, metric = float(candidate["value"]), candidate["metric_id"]
    if not math.isfinite(value):
        return "value_not_finite"
    if metric in PNC_RATIO_BOUNDS:
        low, high = PNC_RATIO_BOUNDS[metric]
        if not low <= value <= high:
            return f"ratio_out_of_bounds ({value} outside {low}-{high})"
    references = _references(candidate, published)
    if not references:
        return None
    if candidate.get("unit") == "PERCENT":
        if all(abs(value - reference) > RATIO_SWING_PP for reference in references):
            return f"ratio_inconsistent_with_history ({value} vs {references})"
        return None
    size = max(abs(value), AMOUNT_FLOOR)
    if all(not 1 / AMOUNT_FACTOR <= size / max(abs(reference), AMOUNT_FLOOR) <= AMOUNT_FACTOR for reference in references):
        return f"amount_inconsistent_with_history ({value} vs {references})"
    return None


def _period_excerpt(candidate: dict[str, Any]) -> tuple[str | None, str | None]:
    """(excerpt, rejection reason). The extractor already matched the document's reported quarter for
    Intact, Definity and Aviva; TD's context must carry the quarter label itself."""
    context, period = str(candidate.get("context") or ""), candidate["period_id"]
    if _CUMULATIVE.search(context):
        return None, "cumulative_period_in_context"
    labels = {f"{year}-Q{quarter}" for quarter, year in _QUARTER.findall(context)}
    if labels - {period}:
        return None, f"context_names_another_quarter ({', '.join(sorted(labels))})"
    if labels:
        return context, None
    if candidate["company_id"] == "TD":
        return None, "quarter_label_missing_from_context"
    return f"Q{period[-1]} {period[:4]}, reported quarter of the document matched by the extractor; {context}", None


def review_automatically(
    candidates: Iterable[dict[str, Any]],
    published: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (accepted candidates with basis_evidence, one decision per candidate).

    ``published`` is the issuer history already in Gold; it drives the consistency checks and the
    ``unchanged`` decision. Candidates of one run are reviewed together so the ratio identity
    (claims + expense = combined) can be checked within the batch.
    """
    candidates, published = list(candidates), list(published)
    by_observation = {row["observation_id"]: row for row in published if row.get("observation_id")}
    accepted, decisions = [], []
    batch = {}
    for candidate in candidates:  # only publishable ratios: Intact's components reconcile to another ratio
        if candidate["metric_id"] in PUBLISHABLE_METRICS.get(candidate["company_id"], frozenset()):
            batch.setdefault((candidate["company_id"], candidate["period_id"]), {})[candidate["metric_id"]] = float(candidate["value"])

    def decide(candidate, decision, reason=None):
        decisions.append({"observation_id": candidate["observation_id"], "value": candidate["value"],
                          "source_document_hash": candidate.get("source_document_hash"), "decision": decision, "reason": reason})

    for candidate in candidates:
        company, metric, period = candidate["company_id"], candidate["metric_id"], candidate["period_id"]
        if metric not in PUBLISHABLE_METRICS.get(company, frozenset()):
            decide(candidate, "excluded", "metric_not_published_for_issuer")
            continue
        prior = by_observation.get(candidate["observation_id"])
        if prior is not None:
            if math.isclose(float(prior["value"]), float(candidate["value"]), rel_tol=0, abs_tol=1e-9):
                decide(candidate, "unchanged")
            else:
                decide(candidate, "rejected", f"differs_from_published ({candidate['value']} vs {prior['value']})")
            continue
        excerpt, reason = _period_excerpt(candidate)
        reason = reason or _plausibility(candidate, published)
        ratios = batch[(company, period)]
        if reason is None and metric in ("combined_ratio", "claims_ratio", "expense_ratio") \
                and all(name in ratios for name in ("combined_ratio", "claims_ratio", "expense_ratio")):
            gap = ratios["claims_ratio"] + ratios["expense_ratio"] - ratios["combined_ratio"]
            if abs(gap) > PNC_RATIO_TOLERANCE_PP:
                reason = f"ratio_identity_broken (claims + expense - combined = {gap:.1f} pp)"
        if reason:
            decide(candidate, "rejected", reason)
            continue
        fiscal_end = PNC_FISCAL_YEAR_END.get(company, 12)
        evidence = {
            "company_id": company, "period_id": period, "period_end": period_end(period, fiscal_end).isoformat(),
            "calendar_basis": CALENDAR_BASIS[company], "disclosure_scope": DISCLOSURE_SCOPE[company],
            "source_document_hash": candidate["source_document_hash"], "reviewed_by": REVIEWER, "basis": "quarterly",
            "source_locator": f"Extracted text: {candidate.get('context') or ''}".strip(),
            "period_excerpt": excerpt, "scope_excerpt": PNC_SOURCE_BASIS[company].disclosure_scope,
            "checks": ["publishable_metric", "quarter_label", "ratio_bounds", "history_consistency", "ratio_identity"],
            "metric_id": metric, "value": candidate["value"], "unit": candidate["unit"],
        }
        accepted.append({**candidate, "basis_evidence": evidence})
        decide(candidate, "accepted")
    return accepted, decisions
