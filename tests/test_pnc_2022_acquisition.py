"""Local checks for 2022 P&C comparative acquisition; no publication."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml

from scripts.submit_pnc_history import checked_manifest
from vigie_databricks.finance_acquisition import FinancialDocumentFetch
from vigie_databricks.finance_documents import create_financial_document
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import extract_pnc_metrics
from vigie_databricks.pnc_history import (
    PNC_REVIEW_STATUS, PNC_VALIDATED_STATUS, validate_pnc_candidate,
)
from vigie_databricks.pnc_live import PncAcquisitionResult, acquire_pnc_documents
from vigie_databricks.tasks import pnc_acquire


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_insurer_contract(ROOT / "config/pnc")


def test_ifc_2022_q2_comparative_skips_row_footnotes():
    report = (
        "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
        "Q2-2023 Q2-2022 Restated 3 Change H1-2023 H1-2022 Restated 3 Change "
        "Combined ratio (discounted) 1 91.4 % 89.1 % "
        "Combined ratio (undiscounted) 2 96.3 % 90.2 % 6.1 pts "
        "Net operating income attributable to common shareholders 2 402 581 (31) % "
        "Net income 260 1,235 (79) % Per share measures"
    )
    rows = {
        row.metric_id: row
        for row in extract_pnc_metrics("IFC", report, CONTRACT, target_period="2022-Q2")
    }
    assert {metric: row.value for metric, row in rows.items()} == pytest.approx({
        "combined_ratio": 90.2,
        "operating_income": 0.581,
        "net_income": 1.235,
    })
    assert "Combined ratio (undiscounted)" in rows["combined_ratio"].context


def test_restated_comparative_context_can_pass_existing_review_gate():
    report = (
        "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
        "Q2-2023 Q2-2022 Restated Change "
        "Combined ratio (undiscounted) 96.3 % 90.2 % Per share measures"
    )
    metric = next(row for row in extract_pnc_metrics(
        "IFC", report, CONTRACT, target_period="2022-Q2"
    ) if row.metric_id == "combined_ratio")
    manifest = yaml.safe_load((ROOT / "config/pnc/history/2022-Q2.yaml").read_text())
    url = next(row["source_url"] for row in manifest["sources"] if row["company_id"] == "IFC")
    source_hash = "a" * 64
    candidate = {
        "company_id": "IFC", "period_id": "2022-Q2", "metric_id": metric.metric_id,
        "value": metric.value, "unit": metric.unit, "source_document_hash": source_hash,
        "source_url": url, "observation_id": "IFC-2022-Q2-combined_ratio",
        "quality_status": "candidate", "validation_status": PNC_REVIEW_STATUS,
        "context": metric.context,
        "basis_evidence": {
            "basis": "quarterly", "period_id": "2022-Q2", "source_document_hash": source_hash,
            "metric_id": metric.metric_id, "value": metric.value, "unit": metric.unit,
            "reviewed_by": "test-reviewer", "source_locator": "Consolidated Highlights",
            "period_excerpt": "Q2-2022", "scope_excerpt": "Intact consolidated P&C operations",
        },
    }
    document = {
        "company_id": "IFC", "reporting_period": "2022-Q2", "content_hash": source_hash,
        "source_url": url, "acquisition_status": "fetched", "document_type": "quarterly_report",
    }
    assert validate_pnc_candidate(candidate, document, CONTRACT) == (PNC_VALIDATED_STATUS, None)


def test_unrestated_comparative_cannot_become_2022_candidate():
    report = (
        "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
        "Q2-2023 Q2-2022 Change Combined ratio (undiscounted) 96.3 % 90.2 % "
        "Per share measures"
    )
    assert extract_pnc_metrics("IFC", report, CONTRACT, target_period="2022-Q2") == []


def test_ifc_restated_header_still_reads_current_2023_quarter():
    report = (
        "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
        "Q2-2023 Q2-2022 Restated 3 Change "
        "Combined ratio (discounted) 1 91.4 % 89.1 % "
        "Combined ratio (undiscounted) 2 96.3 % 90.2 % "
        "Net operating income attributable to common shareholders 2 402 581 "
        "Net income 260 1,235 Per share measures"
    )
    rows = {row.metric_id: row.value for row in extract_pnc_metrics(
        "IFC", report, CONTRACT, target_period="2023-Q2"
    )}
    assert rows["combined_ratio"] == pytest.approx(96.3)
    assert rows["operating_income"] == pytest.approx(0.402)
    assert rows["net_income"] == pytest.approx(0.260)


def test_definity_restated_header_still_reads_current_revenue():
    report = (
        "<h2>Consolidated Results</h2>"
        "<p>(in millions of dollars, except as otherwise noted)</p>"
        "<table><tr><th>Q4 2023</th><th>Q4 2022 (Restated)</th><th>Change</th></tr>"
        "<tr><td>Insurance revenue</td><td>1,003.8</td><td>911.7</td></tr></table>"
        "<h2>Per share measures</h2>"
    )
    rows = {row.metric_id: row.value for row in extract_pnc_metrics(
        "DFY", report, CONTRACT, target_period="2023-Q4"
    )}
    assert rows["insurance_revenue"] == pytest.approx(1.0038)


def test_definity_2022_q1_restated_net_loss_is_reviewable():
    report = (
        "<h2>Consolidated Results</h2>"
        "<p>(in millions of dollars, except as otherwise noted)</p>"
        "<table><tr><th>Q1 2023</th><th>Q1 2022 (Restated)</th><th>Change</th></tr>"
        "<tr><td>Net income (loss) attributable to common shareholders</td>"
        "<td>(48.3)</td><td>(32.6)</td><td>15.7</td></tr></table>"
        "<h2>Per share measures</h2>"
    )
    metric = next(row for row in extract_pnc_metrics(
        "DFY", report, CONTRACT, target_period="2022-Q1"
    ) if row.metric_id == "net_income")
    assert metric.value == pytest.approx(-0.0326)
    url = next(row["source_url"] for row in yaml.safe_load(
        (ROOT / "config/pnc/history/2022-Q1.yaml").read_text()
    )["sources"] if row["company_id"] == "DFY")
    source_hash = "b" * 64
    candidate = {
        "company_id": "DFY", "period_id": "2022-Q1", "metric_id": "net_income",
        "value": metric.value, "unit": metric.unit, "source_document_hash": source_hash,
        "source_url": url, "observation_id": "DFY-2022-Q1-net_income",
        "quality_status": "candidate", "validation_status": PNC_REVIEW_STATUS,
        "context": metric.context,
        "basis_evidence": {
            "basis": "quarterly", "period_id": "2022-Q1", "source_document_hash": source_hash,
            "metric_id": "net_income", "value": metric.value, "unit": metric.unit,
            "reviewed_by": "test-reviewer", "source_locator": "Consolidated Results",
            "period_excerpt": "Q1 2022", "scope_excerpt": "Definity consolidated P&C operations",
        },
    }
    document = {
        "company_id": "DFY", "reporting_period": "2022-Q1", "content_hash": source_hash,
        "source_url": url, "acquisition_status": "fetched", "document_type": "quarterly_report",
    }
    assert validate_pnc_candidate(candidate, document, CONTRACT) == (PNC_VALIDATED_STATUS, None)


def test_2022_q4_acquisition_uses_comparative_not_current_column():
    manifest = yaml.safe_load((ROOT / "config/pnc/history/2022-Q4.yaml").read_text())["sources"]
    reports = {
        "IFC": (
            "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
            "Q4-2023 Q4-2022 Restated 4 Change "
            "Combined ratio (undiscounted) 1 90.1 % 93.2 % "
            "Net operating income attributable to common shareholders 1 752 508 "
            "Net income 531 353 Per share measures"
        ).encode(),
        "DFY": (
            "<h2>Consolidated Results</h2><p>(in millions of dollars, except as otherwise noted)</p>"
            "<table><tr><th>Q4 2023</th><th>Q4 2022 (Restated)</th><th>Change</th></tr>"
            "<tr><td>Insurance revenue</td><td>1,003.8</td><td>911.7</td></tr>"
            "<tr><td>Net income attributable to common shareholders</td>"
            "<td>225.9</td><td>185.0</td></tr></table><h2>Per share measures</h2>"
        ).encode(),
        "TD": b"Wealth Management and Insurance net income was $516 million.",
    }

    def fetch(contract, company, kind, url, **kwargs):
        content = reports[company]
        document = create_financial_document(
            contract, company, kind, url, "fetched", content=content, content_type="text/html"
        )
        return FinancialDocumentFetch(document, content)

    result = acquire_pnc_documents(
        CONTRACT, manifest, document_fetcher=fetch,
        text_extractor=lambda content, kind: content.decode(),
    )
    assert result.errors == {}
    assert {doc.company_id for doc in result.documents} == {"IFC", "TD", "DFY"}
    assert {(row["company_id"], row["metric_id"]): row["value"]
            for row in result.candidates} == pytest.approx({
        ("IFC", "combined_ratio"): 93.2,
        ("IFC", "operating_income"): 0.508,
        ("IFC", "net_income"): 0.353,
        ("DFY", "insurance_revenue"): 0.9117,
        ("DFY", "net_income"): 0.185,
    })
    assert all(row["period_id"] == "2022-Q4" for row in result.candidates)


def test_2022_manifests_validate_and_gap_is_td_only(tmp_path, monkeypatch):
    for quarter in range(1, 5):
        path = ROOT / f"config/pnc/history/2022-Q{quarter}.yaml"
        assert checked_manifest(path) == path.resolve()
    entries = yaml.safe_load((ROOT / "config/pnc/history/2022-Q4.yaml").read_text())
    entries["sources"][0]["expected_no_candidate_reason"] = (
        "standalone_insurance_not_disclosed_in_quarterly_report"
    )
    candidate = tmp_path / "2022-Q4.yaml"
    candidate.write_text(yaml.safe_dump(entries), encoding="utf-8")
    monkeypatch.setattr("scripts.submit_pnc_history.HISTORY", tmp_path.resolve())
    with pytest.raises(ValueError, match="Unsupported expected no-candidate reason"):
        checked_manifest(candidate)


def test_direct_acquisition_rejects_gap_declaration_on_other_issuer():
    manifest = yaml.safe_load((ROOT / "config/pnc/history/2022-Q4.yaml").read_text())[
        "sources"
    ]
    manifest[0]["expected_no_candidate_reason"] = (
        "standalone_insurance_not_disclosed_in_quarterly_report"
    )

    def fetch(*args, **kwargs):
        pytest.fail("invalid manifest must fail before fetching")

    with pytest.raises(ValueError, match="unsupported expected no-candidate reason"):
        acquire_pnc_documents(CONTRACT, manifest, document_fetcher=fetch)


@pytest.mark.parametrize("td_acquired,expected_status", [
    (False, "extraction_incomplete"), (True, "acquired_needs_review"),
])
def test_td_gap_requires_acquired_report(monkeypatch, capsys, td_acquired, expected_status):
    manifest = ROOT / "config/pnc/history/2022-Q4.yaml"
    monkeypatch.setattr(sys, "argv", [
        "pnc_acquire", "--config-directory", str(ROOT / "config/pnc"),
        "--manifest", str(manifest), "--allow-network",
    ])
    documents = (SimpleNamespace(company_id="TD"),) if td_acquired else ()
    result = PncAcquisitionResult(documents, (
        {"company_id": "IFC"}, {"company_id": "DFY"},
    ), {})
    monkeypatch.setattr(pnc_acquire, "acquire_pnc_documents", lambda *args, **kwargs: result)
    if td_acquired:
        pnc_acquire.main()
    else:
        with pytest.raises(SystemExit, match="1"):
            pnc_acquire.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == expected_status
