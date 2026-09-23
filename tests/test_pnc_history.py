from pathlib import Path

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_history import PNC_REVIEW_STATUS, PNC_VALIDATED_STATUS, validate_pnc_candidate
from vigie_databricks.pnc_publication import publish_pnc_candidates


ROOT = Path(__file__).resolve().parents[1]
TD_URL = "https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2026/q2/2026-q2-report-shareholders-en.pdf"


def _document():
    return {
        "company_id": "TD", "reporting_period": "2026-Q2", "content_hash": "a" * 64,
        "source_url": TD_URL, "acquisition_status": "fetched", "document_type": "quarterly_report",
    }


def _candidate(context):
    return {
        "company_id": "TD", "period_id": "2026-Q2", "metric_id": "net_income", "value": 0.279,
        "unit": "CAD_BILLION", "source_document_hash": "a" * 64, "source_url": TD_URL,
        "observation_id": "TD-2026-Q2-net_income", "quality_status": "candidate",
        "basis_evidence": {
            "basis": "quarterly", "period_id": "2026-Q2",
            "source_document_hash": "a" * 64, "metric_id": "net_income",
            "value": 0.279, "unit": "CAD_BILLION", "reviewed_by": "test-reviewer",
            "source_locator": "test report, Insurance section",
            "period_excerpt": "For the quarter ended April 30, 2026",
            "scope_excerpt": "Insurance",
        },
        "context": context, "validation_status": PNC_REVIEW_STATUS,
    }


def test_publication_is_idempotent_and_preserves_history():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    candidate = _candidate("Insurance net income was $279 million.")
    historical = {"observation_id": "TD-2025-Q2-net_income", "value": 0.1}
    first = publish_pnc_candidates([candidate], [_document()], [historical], contract)
    second = publish_pnc_candidates([candidate], [_document()], list(first.observations), contract)
    assert first == second
    assert first.quality_status == "current"
    assert historical in first.observations
    assert len(first.observations) == 2


def test_invalid_batch_preserves_all_last_known_good_values():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    candidate = _candidate("Insurance net income was $279 million.")
    prior = [{"observation_id": "old", "value": 1}]
    bad = {**candidate, "source_document_hash": "b" * 64}
    result = publish_pnc_candidates([candidate, bad], [_document()], prior, contract)
    assert result.quality_status == "stale"
    assert result.observations == tuple(prior)
    assert "duplicate_observation_id" in result.rejection_reasons
    assert "source_document_not_acquired" in result.rejection_reasons


def test_manifest_period_alone_never_authorizes_publication():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    candidate = _candidate("Insurance net income was $279 million.")
    candidate.pop("basis_evidence")
    assert validate_pnc_candidate(candidate, _document(), contract) == (
        "rejected", "accounting_basis_unverified"
    )


def test_half_year_and_trailing_values_are_rejected():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    for basis in ("half_year", "year_to_date", "trailing_12_months"):
        candidate = _candidate("Insurance net income was $279 million.")
        candidate["basis_evidence"]["basis"] = basis
        assert validate_pnc_candidate(candidate, _document(), contract) == (
            "rejected", "non_quarterly_accounting_basis"
        )


def test_quarterly_claim_does_not_override_cumulative_source_excerpt():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    for excerpt in ("Six months 2026", "HY26", "H1 2026", "2026-Q2, year-to-date",
                    "Q2 2026 and full year 2025"):
        candidate = _candidate("Insurance net income was $279 million.")
        candidate["basis_evidence"]["period_excerpt"] = excerpt
        assert validate_pnc_candidate(candidate, _document(), contract) == (
            "rejected", "quarterly_period_evidence_mismatch"
        )


def test_quarterly_period_excerpt_must_identify_matching_period():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    for excerpt in ("Q1 2026", "Q2 2025", "Results released in 2026",
                    "Quarterly 2026", "Three months ended April 30 2025, reported 2026"):
        candidate = _candidate("Insurance net income was $279 million.")
        candidate["basis_evidence"]["period_excerpt"] = excerpt
        assert validate_pnc_candidate(candidate, _document(), contract) == (
            "rejected", "quarterly_period_evidence_mismatch"
        )


def test_quarterly_period_excerpt_accepts_reviewed_source_formats():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    for excerpt in ("Q2-2026", "2026-Q2", "For the three months ended April 30 2026"):
        candidate = _candidate("Insurance net income was $279 million.")
        candidate["basis_evidence"]["period_excerpt"] = excerpt
        assert validate_pnc_candidate(candidate, _document(), contract) == (
            PNC_VALIDATED_STATUS, None
        )


def test_reviewed_evidence_cannot_be_reused_for_another_value():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    candidate = _candidate("Insurance net income was $279 million.")
    candidate["value"] = 0.837
    assert validate_pnc_candidate(candidate, _document(), contract) == (
        "rejected", "basis_evidence_value_mismatch"
    )


def test_accepts_traceable_td_insurance_only_candidate():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    assert validate_pnc_candidate(_candidate("Insurance net income was $279 million."), _document(), contract) == (
        PNC_VALIDATED_STATUS, None
    )


def test_rejects_td_combined_segment_candidate_even_from_official_report():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    assert validate_pnc_candidate(
        _candidate("Wealth Management and Insurance net income was $837 million."), _document(), contract
    ) == ("rejected", "pnc_disclosure_scope_prohibited")
