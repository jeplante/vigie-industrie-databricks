"""Validation gates for historical Finance observations before publication."""

from __future__ import annotations

from typing import Any


REVIEW_STATUS = "needs_period_and_accounting_basis_review"
VALIDATED_STATUS = "validated_quarterly"


def validate_historical_candidate(candidate: dict[str, Any], document: dict[str, Any] | None) -> tuple[str, str | None]:
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
    checks = {
        "company_id": candidate.get("company_id") == document.get("company_id"),
        "reporting_period": period == document.get("reporting_period"),
        "content_hash": candidate.get("source_document_hash") == document.get("content_hash"),
        "source_url": candidate.get("source_url") == document.get("source_url"),
    }
    for name, matches in checks.items():
        if not matches:
            return "rejected", f"source_{name}_mismatch"
    return VALIDATED_STATUS, None


def history_basis(metric_id: str) -> str:
    """Metrics that can safely be summed inside a reporting year for a YTD chart."""
    return "additive" if metric_id in {"core_earnings", "net_income", "new_business_value", "ape_sales"} else "point_in_time"
