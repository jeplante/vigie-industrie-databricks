"""Validation gate for P&C candidates before any P&C Gold publication."""

from __future__ import annotations

import math
import re
from typing import Any

from vigie_databricks.finance_history import VALUE_RANGES
from vigie_databricks.insurer_contract import InsurerContract, parse_finance_observation_candidate
from vigie_databricks.pnc_extraction import PNC_ALIASES
from vigie_databricks.pnc_provenance import validate_pnc_source_basis


PNC_REVIEW_STATUS = "needs_period_and_accounting_basis_review"
PNC_VALIDATED_STATUS = "validated_quarterly"


def validate_pnc_candidate(
    candidate: dict[str, Any], document: dict[str, Any] | None, contract: InsurerContract
) -> tuple[str, str | None]:
    """Accept only traceable, explicitly scoped quarterly P&C observations."""
    if candidate.get("validation_status") != PNC_REVIEW_STATUS:
        return "rejected", "candidate_not_in_review"
    period = str(candidate.get("period_id") or "")
    if not re.fullmatch(r"20\d{2}-Q[1-4]", period):
        return "rejected", "non_quarterly_period"
    if not document or document.get("acquisition_status") not in {"fetched", "unchanged"}:
        return "rejected", "source_document_not_acquired"
    if document.get("document_type") != "quarterly_report":
        return "rejected", "source_document_not_quarterly"
    key_map = {
        "company_id": "company_id",
        "period_id": "reporting_period",
        "source_document_hash": "content_hash",
        "source_url": "source_url",
    }
    for candidate_key, document_key in key_map.items():
        if candidate.get(candidate_key) != document.get(document_key):
            return "rejected", f"source_{document_key}_mismatch"
    if not re.fullmatch(r"[a-f0-9]{64}", str(document.get("content_hash") or "")):
        return "rejected", "source_hash_invalid"
    # A manifest/filename period is only a discovery hint. Publication needs
    # independently reviewed evidence from the report, tied to this revision.
    evidence = candidate.get("basis_evidence")
    if not isinstance(evidence, dict):
        return "rejected", "accounting_basis_unverified"
    if evidence.get("basis") != "quarterly":
        return "rejected", "non_quarterly_accounting_basis"
    for key, expected in {
        "period_id": period,
        "source_document_hash": document["content_hash"],
        "metric_id": candidate.get("metric_id"),
        "value": candidate.get("value"),
        "unit": candidate.get("unit"),
    }.items():
        if evidence.get(key) != expected:
            return "rejected", f"basis_evidence_{key}_mismatch"
    if not all(isinstance(evidence.get(key), str) and evidence[key].strip()
               for key in ("reviewed_by", "source_locator", "period_excerpt", "scope_excerpt")):
        return "rejected", "basis_evidence_incomplete"
    company_id = str(candidate.get("company_id") or "")
    metric_id = str(candidate.get("metric_id") or "")
    if company_id not in PNC_ALIASES or metric_id not in PNC_ALIASES[company_id]:
        return "rejected", "metric_not_expected_for_company"
    try:
        parsed = parse_finance_observation_candidate(candidate, contract)
    except ValueError:
        return "rejected", "candidate_contract_mismatch"
    if not math.isfinite(parsed.value):
        return "rejected", "metric_value_not_finite"
    lower, upper = VALUE_RANGES[parsed.unit]
    if not lower <= parsed.value <= upper:
        return "rejected", "metric_value_out_of_range"
    context = str(candidate.get("context") or "")
    aliases = PNC_ALIASES[company_id][metric_id]
    if not context or not any(re.search(re.escape(alias), context, re.IGNORECASE) for alias in aliases):
        return "rejected", "metric_context_missing_alias"
    valid_basis, reason = validate_pnc_source_basis(
        company_id, str(candidate["source_url"]), evidence["scope_excerpt"] + " " + context, contract
    )
    if not valid_basis:
        return "rejected", reason
    return PNC_VALIDATED_STATUS, None
