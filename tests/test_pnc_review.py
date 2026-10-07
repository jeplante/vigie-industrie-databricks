from pathlib import Path

import yaml

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import PNC_ALIASES
from vigie_databricks.pnc_history import PNC_REVIEW_STATUS
from vigie_databricks.pnc_publication import publish_pnc_candidates
from vigie_databricks.pnc_review import (
    attach_reviewed_evidence,
    review_pnc_candidates,
    select_reviewed_periods,
)


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


def test_select_reviewed_periods_keeps_only_requested_periods_in_order():
    reviews = [{"period_id": "2022-Q1"}, {"period_id": "2023-Q1"}, {"period_id": "2022-Q2"}]

    assert select_reviewed_periods(reviews, ["2022-Q2", "2022-Q1"]) == [reviews[0], reviews[2]]
    assert select_reviewed_periods(reviews) == reviews


def test_select_reviewed_periods_rejects_invalid_duplicate_or_unmatched_periods():
    reviews = [{"period_id": "2022-Q1"}]

    for periods in ([], ["2022-02"], ["2022-Q1", "2022-Q1"], ["2022-Q2"]):
        try:
            select_reviewed_periods(reviews, periods)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid selection to fail: {periods}")


def test_2022_review_evidence_covers_only_the_approved_ifc_and_dfy_candidates():
    root = Path(__file__).resolve().parents[1]
    reviews = yaml.safe_load((root / "config/pnc/reviewed_evidence.yaml").read_text())["reviews"]
    selected = select_reviewed_periods(reviews, [f"2022-Q{quarter}" for quarter in range(1, 5)])
    metric_keys = [
        (review["company_id"], review["period_id"], review["source_document_hash"], metric)
        for review in selected
        for metric in review["metrics"]
    ]

    assert len(selected) == 8
    assert len(metric_keys) == 36
    assert len(set(metric_keys)) == 36
    assert {review["company_id"] for review in selected} == {"IFC", "DFY"}
    assert all(review["reviewed_by"] == "jerome.plante@hotmail.com" for review in selected)
    assert all(review["approval_reference"] == "explicit user approval, 2026-10-03" for review in selected)


def test_2022_approved_evidence_passes_the_reviewed_publication_gate():
    root = Path(__file__).resolve().parents[1]
    config = root / "config/pnc"
    reviews = yaml.safe_load((config / "reviewed_evidence.yaml").read_text())["reviews"]
    selected = select_reviewed_periods(reviews, [f"2022-Q{quarter}" for quarter in range(1, 5)])
    candidates = []
    documents = []
    for review in selected:
        manifest = yaml.safe_load((config / "history" / f"{review['period_id']}.yaml").read_text())
        source = next(item for item in manifest["sources"] if item.get("company_id") == review["company_id"])
        documents.append({
            "company_id": review["company_id"],
            "reporting_period": review["period_id"],
            "content_hash": review["source_document_hash"],
            "source_url": source["source_url"],
            "acquisition_status": "fetched",
            "document_type": "quarterly_report",
        })
        for metric_id, metric in review["metrics"].items():
            aliases = PNC_ALIASES[review["company_id"]][metric_id]
            candidates.append({
                "company_id": review["company_id"],
                "period_id": review["period_id"],
                "metric_id": metric_id,
                "value": metric["value"],
                "unit": metric["unit"],
                "source_document_hash": review["source_document_hash"],
                "source_url": source["source_url"],
                "observation_id": f"{review['company_id']}-{review['period_id']}-{metric_id}",
                "context": "; ".join(aliases),
                "quality_status": "candidate",
                "validation_status": PNC_REVIEW_STATUS,
            })

    candidates = attach_reviewed_evidence(candidates, selected)
    result = publish_pnc_candidates(candidates, documents, [], load_insurer_contract(config))

    assert result.quality_status == "current", result.rejection_reasons
    assert len(result.observations) == 36
    assert len({row["observation_id"] for row in result.observations}) == 36
    assert {row["period_id"] for row in result.observations} == {
        f"2022-Q{quarter}" for quarter in range(1, 5)
    }
    assert all(row["basis_evidence"]["reviewed_by"] == "jerome.plante@hotmail.com"
               for row in result.observations)


def test_identical_repersisted_candidates_collapse_but_conflicts_survive():
    from vigie_databricks.pnc_review import collapse_identical_candidates
    base = dict(observation_id="TD-2026-Q2-net_income", source_document_hash="h1", value=0.279, unit="CAD_BILLION")
    rows = [dict(base, candidate_id="a"), dict(base, candidate_id="b")]
    assert [row["candidate_id"] for row in collapse_identical_candidates(rows)] == ["a"]
    conflicting = rows + [dict(base, candidate_id="c", value=0.28), dict(base, candidate_id="d", source_document_hash="h2")]
    assert [row["candidate_id"] for row in collapse_identical_candidates(conflicting)] == ["a", "c", "d"]
