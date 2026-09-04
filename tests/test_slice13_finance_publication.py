from pathlib import Path

from vigie_databricks.finance_publication import publish_finance_candidates
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


def test_invalid_candidate_preserves_last_known_good_snapshot():
    prior = [{"observation_id": "MFC-2025-Q4-core_earnings", "value": 1.5}]
    invalid = [{"observation_id": "MFC-2026-Q1-core_earnings", "company_id": "MFC"}]
    result = publish_finance_candidates(invalid, prior, load_insurer_contract(ROOT / "config"))
    assert result.observations == tuple(prior)
    assert result.quality_status == "stale"
    assert result.rejection_reasons


def test_valid_candidate_batch_becomes_current_snapshot():
    candidate = {"observation_id": "MFC-2026-Q1-core_earnings", "company_id": "MFC", "metric_id": "core_earnings", "period_id": "2026-Q1", "value": 1.8, "unit": "CAD_BILLION", "source_url": "https://www.manulife.com/ca/en/about-us/investors/results-and-reports", "source_document_hash": "x", "quality_status": "candidate"}
    result = publish_finance_candidates([candidate], [], load_insurer_contract(ROOT / "config"))
    assert result.quality_status == "current"
    assert result.observations == (candidate,)