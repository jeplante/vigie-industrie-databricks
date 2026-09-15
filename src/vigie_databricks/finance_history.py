"""Validation gates for historical Finance observations before publication."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

from vigie_databricks.finance_discovery import financial_document_preference
from vigie_databricks.finance_extraction import ALIASES, EXPECTED_METRICS
from vigie_databricks.insurer_contract import InsurerContract, parse_finance_observation_candidate


REVIEW_STATUS = "needs_period_and_accounting_basis_review"
VALIDATED_STATUS = "validated_quarterly"
REVIEWED_VARIANCE_STATUS = "validated_quarterly_reviewed_variance"
# Values independently confirmed in two official reports but exceeding the
# conservative year-over-year screen. Keep the trace and quality distinction;
# do not silently suppress the signal or discard a published value.
REVIEWED_VARIANCES = {
    ("IAG", "net_income", "2024-Q3"): "officially_verified_variance_vs_2023-Q3",
}


VALUE_RANGES = {
    "CAD_PER_SHARE": (0.0, 100.0),
    "CAD_MILLION": (0.0, 1_000_000.0),
    "CAD_BILLION": (0.0, 10_000.0),
    "CAD_TRILLION": (0.0, 100.0),
    "PERCENT": (0.0, 500.0),
}


def select_preferred_documents(documents: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Select the strongest eligible source for every insurer-quarter."""
    selected: dict[tuple[str, str], tuple[tuple[int, str, str], dict[str, Any]]] = {}
    for document in documents:
        company = str(document.get("company_id") or "")
        period = str(document.get("reporting_period") or "")
        url = str(document.get("source_url") or "")
        preference = financial_document_preference(url)
        if not company or not re.fullmatch(r"20\d{2}-Q[1-4]", period) or preference < 0:
            continue
        fetched_at = str(document.get("fetched_at") or "")
        rank = (preference, fetched_at, url)
        key = (company, period)
        if key not in selected or rank > selected[key][0]:
            selected[key] = (rank, document)
    return {key: value[1] for key, value in selected.items()}


def validate_historical_candidate(
    candidate: dict[str, Any], document: dict[str, Any] | None, contract: InsurerContract | None = None
) -> tuple[str, str | None]:
    """Accept only traceable quarterly candidates; annual and ambiguous inputs stay out of Gold."""
    if candidate.get("validation_status") != REVIEW_STATUS:
        return "rejected", "candidate_not_in_review"
    period = str(candidate.get("period_id") or "")
    if not period.endswith(("-Q1", "-Q2", "-Q3", "-Q4")):
        return "rejected", "non_quarterly_period"
    if not document:
        return "rejected", "source_document_missing"
    if document.get("acquisition_status") not in {"fetched", "unchanged"}:
        return "rejected", "source_document_not_acquired"
    if document.get("document_type") != "quarterly_report":
        return "rejected", "source_document_not_quarterly"
    if financial_document_preference(str(document.get("source_url") or "")) < 0:
        return "rejected", "source_document_disallowed"
    checks = {
        "company_id": candidate.get("company_id") == document.get("company_id"),
        "reporting_period": period == document.get("reporting_period"),
        "content_hash": candidate.get("source_document_hash") == document.get("content_hash"),
        "source_url": candidate.get("source_url") == document.get("source_url"),
    }
    for name, matches in checks.items():
        if not matches:
            return "rejected", f"source_{name}_mismatch"
    company_id = str(candidate.get("company_id") or "")
    metric_id = str(candidate.get("metric_id") or "")
    if metric_id not in EXPECTED_METRICS.get(company_id, ()):
        return "rejected", "metric_not_expected_for_company"
    value = candidate.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        return "rejected", "metric_value_not_finite"
    if contract is not None:
        try:
            parsed = parse_finance_observation_candidate(candidate, contract)
        except ValueError:
            return "rejected", "candidate_contract_mismatch"
        lower, upper = VALUE_RANGES[parsed.unit]
        if not lower <= parsed.value <= upper:
            return "rejected", "metric_value_out_of_range"
    context = str(candidate.get("context") or "")
    aliases = ALIASES.get(company_id, {}).get(metric_id, ())
    if not context or not any(re.search(re.escape(alias), context, re.IGNORECASE) for alias in aliases):
        return "rejected", "metric_context_missing_alias"
    return VALIDATED_STATUS, None


def incomplete_periods(
    candidates: Iterable[dict[str, Any]], expected_periods: Iterable[tuple[str, str]] = ()
) -> dict[tuple[str, str], tuple[str, ...]]:
    """Return missing expected KPIs for each insurer-quarter represented by candidates."""
    present: dict[tuple[str, str], set[str]] = {key: set() for key in expected_periods}
    for candidate in candidates:
        if candidate.get("validation_status") not in {VALIDATED_STATUS, REVIEWED_VARIANCE_STATUS}:
            continue
        key = (str(candidate.get("company_id")), str(candidate.get("period_id")))
        present.setdefault(key, set()).add(str(candidate.get("metric_id")))
    return {
        key: tuple(sorted(EXPECTED_METRICS[key[0]] - metrics))
        for key, metrics in present.items()
        if key[0] in EXPECTED_METRICS and EXPECTED_METRICS[key[0]] - metrics
    }


def anomalous_observations(candidates: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Flag extreme same-quarter year-over-year changes for manual review."""
    rows = [row for row in candidates if row.get("validation_status") == VALIDATED_STATUS]
    by_key = {(str(row["company_id"]), str(row["metric_id"]), str(row["period_id"])): row for row in rows}
    anomalies: dict[str, str] = {}
    for row in rows:
        period = str(row["period_id"])
        previous_period = f"{int(period[:4]) - 1}{period[4:]}"
        previous = by_key.get((str(row["company_id"]), str(row["metric_id"]), previous_period))
        if previous is None:
            continue
        current_value, previous_value = float(row["value"]), float(previous["value"])
        metric_id = str(row["metric_id"])
        if metric_id in {"core_roe", "licat_ratio"}:
            suspicious = abs(current_value - previous_value) > 30.0
        elif previous_value == 0:
            suspicious = current_value != 0
        else:
            threshold = 3.0 if metric_id == "net_income" else 1.0
            suspicious = abs(current_value - previous_value) / abs(previous_value) > threshold
        if suspicious:
            anomalies[str(row["observation_id"])] = f"extreme_yoy_change_vs_{previous_period}"
    return anomalies


def history_basis(metric_id: str) -> str:
    """Metrics that can safely be summed inside a reporting year for a YTD chart."""
    return "additive" if metric_id in {"core_earnings", "net_income", "new_business_value", "ape_sales"} else "point_in_time"
