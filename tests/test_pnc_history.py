from pathlib import Path

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_history import PNC_REVIEW_STATUS, PNC_VALIDATED_STATUS, validate_pnc_candidate


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
        "context": context, "validation_status": PNC_REVIEW_STATUS,
    }


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
