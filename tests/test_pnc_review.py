from pathlib import Path

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_review import review_pnc_candidates
from vigie_databricks.pnc_review import attach_reviewed_evidence


def test_review_exposes_conflicts_and_missing_companies_without_approving():
    contract = load_insurer_contract(Path(__file__).resolve().parents[1] / "config/pnc")
    row = dict(company_id="TD", observation_id="TD-2026-Q2-net_income", value=.279, unit="CAD_BILLION")
    report = review_pnc_candidates([row, {**row, "value": .837}], [], contract)
    assert not report["published"]
    assert all(r["reason"] == "conflicting_observation_values" for r in report["candidates"])
    assert report["coverage"]["TD"] == {"candidate_count": 2, "eligible_count": 0}
    assert report["coverage"]["AV"] == {"candidate_count": 0, "eligible_count": 0}


def test_review_is_bound_to_value_unit_and_revision():
    candidate = dict(company_id="DFY", period_id="2026-Q2", metric_id="net_income",
                     source_document_hash="a" * 64, value=.1524, unit="CAD_BILLION")
    review = {**candidate, "metrics": {"net_income": {"value": .1524, "unit": "CAD_BILLION"}}}
    assert "basis_evidence" in attach_reviewed_evidence([candidate], [review])[0]
    for change in ({"value": .2163}, {"unit": "CAD_MILLION"}, {"source_document_hash": "b" * 64}):
        assert "basis_evidence" not in attach_reviewed_evidence([{**candidate, **change}], [review])[0]
