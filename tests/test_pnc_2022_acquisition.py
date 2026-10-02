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


@pytest.mark.parametrize(
    ("quarter", "current_ratio", "prior_ratio", "current_operating", "prior_operating",
     "current_net", "prior_net"),
    [
        ("Q1", 91.9, 92.1, 537, 516, 377, 487),
        ("Q2", 96.3, 90.2, 402, 581, 260, 1235),
        ("Q3", 98.3, 91.7, 370, 488, 163, 375),
    ],
)
def test_ifc_q1_to_q3_comparative_reads_restated_2022_values(
    quarter, current_ratio, prior_ratio, current_operating, prior_operating, current_net, prior_net
):
    # Official IFC releases with 2022 restated comparatives:
    # Q1 https://newsroom.intactfc.com/2023-05-10-Intact-Financial-Corporation-reports-Q1-2023-results-under-IFRS-17
    # Q2 https://www.newswire.ca/news-releases/intact-financial-corporation-reports-q2-2023-results-803908690.html
    # Q3 https://www.newswire.ca/news-releases/intact-financial-corporation-reports-q3-2023-results-882833147.html
    cumulative = {
        "Q2": ("H1-2023 H1-2022 Restated Change", 94.2, 91.2, 939, 1097, 637, 1722),
        "Q3": ("YTD 2023 YTD 2022 Restated Change", 95.6, 91.3, 1309, 1585, 800, 2097),
    }.get(quarter)
    trailing_headers = ""
    ratio_trailing = operating_trailing = net_trailing = ""
    if cumulative:
        (trailing_headers, ytd_current_ratio, ytd_prior_ratio, ytd_current_operating,
         ytd_prior_operating, ytd_current_net, ytd_prior_net) = cumulative
        ratio_trailing = f" {ytd_current_ratio:.1f} % {ytd_prior_ratio:.1f} % Change"
        operating_trailing = f" {ytd_current_operating} {ytd_prior_operating} Change"
        net_trailing = f" {ytd_current_net:,} {ytd_prior_net:,} Change"
    report = (
        "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
        f"{quarter}-2023 {quarter}-2022 Restated Change {trailing_headers} "
        f"Combined ratio (undiscounted) {current_ratio:.1f} % {prior_ratio:.1f} %{ratio_trailing} "
        f"Net operating income attributable to common shareholders {current_operating} "
        f"{prior_operating} Change{operating_trailing} "
        f"Net income {current_net:,} {prior_net:,} Change{net_trailing} "
        "Per share measures"
    )
    metrics = extract_pnc_metrics("IFC", report, CONTRACT, target_period=f"2022-{quarter}")
    assert len(metrics) == 3
    rows = {row.metric_id: row for row in metrics}
    assert set(rows) == {"combined_ratio", "operating_income", "net_income"}
    assert {metric: row.value for metric, row in rows.items()} == pytest.approx({
        "combined_ratio": prior_ratio,
        "operating_income": prior_operating / 1000,
        "net_income": prior_net / 1000,
    })
    assert all(f"{quarter}-2022" in row.context for row in rows.values())


@pytest.mark.parametrize(
    ("quarter", "revenue", "claims", "expenses", "combined", "operating", "net"),
    [
        ("Q1", 814.3, 59.1, 33.3, 92.4, 63.3, -32.6),
        ("Q2", 863.8, 63.3, 32.0, 95.3, 51.1, -77.2),
        ("Q3", 895.9, 64.7, 32.0, 96.7, 45.8, 35.7),
    ],
)
def test_definity_q1_to_q3_comparative_reads_restated_2022_values(
    quarter, revenue, claims, expenses, combined, operating, net
):
    # Official Definity releases with 2022 restated comparatives:
    # Q1 https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2023/Definity-Reports-First-Quarter-2023-Results/default.aspx
    # Q2 https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2023/Definity-Financial-Corporation-Reports-Second-Quarter-2023-Results/default.aspx
    # Q3 https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2023/Definity-Reports-Third-Quarter-2023-Results/default.aspx
    current = {
        "Q1": (907.5, 62.6, 32.7, 95.3, 63.4, 100.9),
        "Q2": (954.9, 63.7, 31.6, 95.3, 64.8, 71.6),
        "Q3": (984.1, 72.9, 29.6, 102.5, 17.6, -48.3),
    }[quarter]
    ytd = {
        "Q2": (1862.4, 1678.1, 63.2, 61.2, 32.1, 32.7, 95.3, 93.9,
               128.2, 114.4, 172.5, -109.8),
        "Q3": (2846.5, 2574.0, 66.5, 62.4, 31.3, 32.5, 97.8, 94.9,
               145.8, 160.2, 124.2, -74.1),
    }.get(quarter)
    ytd_headers = ""
    ytd_cells = {metric: "" for metric in
                 ("revenue", "claims", "expenses", "combined", "operating", "net")}
    if ytd:
        (ytd_revenue, prior_ytd_revenue, ytd_claims, prior_ytd_claims,
         ytd_expenses, prior_ytd_expenses, ytd_combined, prior_ytd_combined,
         ytd_operating, prior_ytd_operating, ytd_net, prior_ytd_net) = ytd
        ytd_headers = "<th>2023 YTD</th><th>2022 YTD<br>(Restated)</th><th>Change</th>"
        ytd_cells = {
            "revenue": f"<td>{ytd_revenue:.1f}</td><td>{prior_ytd_revenue:.1f}</td><td>Change</td>",
            "claims": f"<td>{ytd_claims:.1f}%</td><td>{prior_ytd_claims:.1f}%</td><td>Change</td>",
            "expenses": f"<td>{ytd_expenses:.1f}%</td><td>{prior_ytd_expenses:.1f}%</td><td>Change</td>",
            "combined": f"<td>{ytd_combined:.1f}%</td><td>{prior_ytd_combined:.1f}%</td><td>Change</td>",
            "operating": f"<td>{ytd_operating:.1f}</td><td>{prior_ytd_operating:.1f}</td><td>Change</td>",
            "net": f"<td>{ytd_net:.1f}</td><td>{prior_ytd_net:.1f}</td><td>Change</td>",
        }
    current_revenue, current_claims, current_expenses, current_combined, current_operating, current_net = current
    comparative_net = f"({abs(net):.1f})" if net < 0 else f"{net:.1f}"
    current_net_text = f"({abs(current_net):.1f})" if current_net < 0 else f"{current_net:.1f}"
    net_label = "Net income (loss)" if quarter in {"Q1", "Q2"} else "Net (loss) income"
    report = (
        "<h2>Consolidated Results</h2><p>(in millions of dollars, except as otherwise noted)</p>"
        "<table><tr><th></th>"
        f"<th>{quarter} 2023</th><th>{quarter} 2022<br>(Restated)</th><th>Change</th>"
        f"{ytd_headers}</tr>"
        f"<tr><td>Insurance revenue</td><td>{current_revenue:.1f}</td><td>{revenue:.1f}</td>"
        f"<td>Change</td>{ytd_cells['revenue']}</tr>"
        f"<tr><td>Claims ratio</td><td>{current_claims:.1f}%</td><td>{claims:.1f}%</td>"
        f"<td>Change</td>{ytd_cells['claims']}</tr>"
        f"<tr><td>Expense ratio</td><td>{current_expenses:.1f}%</td><td>{expenses:.1f}%</td>"
        f"<td>Change</td>{ytd_cells['expenses']}</tr>"
        f"<tr><td>Combined ratio</td><td>{current_combined:.1f}%</td><td>{combined:.1f}%</td>"
        f"<td>Change</td>{ytd_cells['combined']}</tr>"
        f"<tr><td>Operating net income</td><td>{current_operating:.1f}</td><td>{operating:.1f}</td>"
        f"<td>Change</td>{ytd_cells['operating']}</tr>"
        f"<tr><td>{net_label} attributable to common shareholders</td>"
        f"<td>{current_net_text}</td><td>{comparative_net}</td><td>Change</td>"
        f"{ytd_cells['net']}</tr></table>"
        "<h2>Per share measures</h2>"
    )
    metrics = extract_pnc_metrics("DFY", report, CONTRACT, target_period=f"2022-{quarter}")
    assert len(metrics) == 6
    rows = {row.metric_id: row for row in metrics}
    assert set(rows) == {
        "insurance_revenue", "claims_ratio", "expense_ratio", "combined_ratio",
        "operating_income", "net_income",
    }
    assert {metric: row.value for metric, row in rows.items()} == pytest.approx({
        "insurance_revenue": revenue / 1000,
        "claims_ratio": claims,
        "expense_ratio": expenses,
        "combined_ratio": combined,
        "operating_income": operating / 1000,
        "net_income": net / 1000,
    })
    assert all(f"{quarter} 2022" in row.context for row in rows.values())


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
