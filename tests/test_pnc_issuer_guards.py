"""Issuer-specific quarterly P&C extraction guards."""

from pathlib import Path

import pytest

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import extract_pnc_metrics
from vigie_databricks.pnc_history import PNC_REVIEW_STATUS, PNC_VALIDATED_STATUS, validate_pnc_candidate


CONTRACT = load_insurer_contract(Path(__file__).resolve().parents[1] / "config/pnc")


def test_definity_current_quarter_loss_uses_parenthesized_table_value():
    report = (
        "<h2>Consolidated Results</h2><p>(in millions of dollars, except as otherwise noted)</p>"
        "<table><tr><th>Q3 2023</th><th>Q3 2022 (Restated)</th><th>Change</th></tr>"
        "<tr><td>Net (loss) income attributable to common shareholders</td>"
        "<td>(48.3)</td><td>35.7</td><td>(84.0)</td></tr></table>"
        "<h2>Per share measures</h2>"
    )
    rows = extract_pnc_metrics("DFY", report, CONTRACT, target_period="2023-Q3")
    net_income = next(row for row in rows if row.metric_id == "net_income")
    assert net_income.value == pytest.approx(-0.0483)
    assert "Q3 2023" in net_income.context
    assert "(48.3)" in net_income.context


def test_aviva_uses_only_canada_undiscounted_cor_column():
    report = (
        "Discounted COR Undiscounted COR Q124 Q123 Change Q124 Q123 Change "
        "UK 93.9 % 95.1 % (1.2) pp 97.3 % 98.4 % (1.1) pp "
        "Canada 89.4 % 88.6 % 0.8 pp 93.7 % 92.4 % 1.3 pp "
        "Total 92.0 % 91.8 % 0.2 pp 95.8 % 95.4 % 0.4 pp"
    )
    rows = extract_pnc_metrics("AV", report, CONTRACT, target_period="2024-Q1")
    ratio = next(row for row in rows if row.metric_id == "combined_ratio")
    assert ratio.value == pytest.approx(93.7)
    assert "Canada" in ratio.context
    assert "undiscounted" in ratio.context.lower()


def test_aviva_cannot_relabel_a_different_quarter_or_group_ratio():
    report = (
        "Discounted COR Undiscounted COR Q124 Q123 Change Q124 Q123 Change "
        "Canada 89.4 % 88.6 % 0.8 pp 93.7 % 92.4 % 1.3 pp "
        "Total 92.0 % 91.8 % 0.2 pp 95.8 % 95.4 % 0.4 pp"
    )
    rows = extract_pnc_metrics("AV", report, CONTRACT, target_period="2023-Q1")
    assert "combined_ratio" not in {row.metric_id for row in rows}


def test_aviva_does_not_borrow_canada_row_from_later_quarter_table():
    report = (
        "Discounted COR Undiscounted COR Q124 Q123 Change Q124 Q123 Change "
        "Total 92.0 % 91.8 % 0.2 pp 95.8 % 95.4 % 0.4 pp "
        "Discounted COR Undiscounted COR Q224 Q223 Change Q224 Q223 Change "
        "Canada 87.0 % 89.0 % (2.0) pp 90.0 % 92.0 % (2.0) pp"
    )
    rows = extract_pnc_metrics("AV", report, CONTRACT, target_period="2024-Q1")
    assert "combined_ratio" not in {row.metric_id for row in rows}


def test_aviva_quarterly_candidate_passes_review_gate_with_scope_evidence():
    report = (
        "Discounted COR Undiscounted COR Q124 Q123 Change Q124 Q123 Change "
        "Canada 89.4 % 88.6 % 0.8 pp 93.7 % 92.4 % 1.3 pp"
    )
    metric = next(row for row in extract_pnc_metrics(
        "AV", report, CONTRACT, target_period="2024-Q1"
    ) if row.metric_id == "combined_ratio")
    source_url = "https://static.aviva.io/content/dam/aviva-corporate/documents/investors/pdfs/results/2024/Aviva-Q1-trading-update.pdf"
    source_hash = "a" * 64
    candidate = {
        "company_id": "AV", "period_id": "2024-Q1", "metric_id": metric.metric_id,
        "value": metric.value, "unit": metric.unit, "source_document_hash": source_hash,
        "source_url": source_url, "observation_id": "AV-2024-Q1-combined_ratio",
        "quality_status": "candidate", "validation_status": PNC_REVIEW_STATUS,
        "context": metric.context,
        "basis_evidence": {
            "basis": "quarterly", "period_id": "2024-Q1", "source_document_hash": source_hash,
            "metric_id": metric.metric_id, "value": metric.value, "unit": metric.unit,
            "reviewed_by": "test-reviewer", "source_locator": "Canada General Insurance COR table",
            "period_excerpt": "Q1 2024", "scope_excerpt": "Aviva Canada general insurance",
        },
    }
    document = {
        "company_id": "AV", "reporting_period": "2024-Q1", "content_hash": source_hash,
        "source_url": source_url, "acquisition_status": "fetched",
        "document_type": "quarterly_report",
    }
    assert validate_pnc_candidate(candidate, document, CONTRACT) == (PNC_VALIDATED_STATUS, None)


def test_intact_discounted_claims_components_are_not_comparable_candidates():
    report = (
        "Consolidated Highlights (in millions of Canadian dollars except as otherwise noted) "
        "Q4-2023 Q4-2022 Restated Change "
        "Combined ratio (discounted) 85.0 % 90.4 % "
        "Combined ratio (undiscounted) 90.1 % 93.2 % "
        "Claims ratio 52.5 % Expense ratio 32.5 % Per share measures"
    )
    rows = extract_pnc_metrics("IFC", report, CONTRACT, target_period="2023-Q4")
    assert {row.metric_id for row in rows}.isdisjoint({"claims_ratio", "expense_ratio"})
    assert next(row for row in rows if row.metric_id == "combined_ratio").value == pytest.approx(90.1)


def test_td_prior_quarter_catastrophe_amount_does_not_become_current_candidate():
    report = (
        "For the three months ended January 31 2025, catastrophe claims were nil. "
        "For Q4 2024, catastrophe claims $1,020 million."
    )
    rows = extract_pnc_metrics("TD", report, CONTRACT, target_period="2025-Q1")
    assert "catastrophe_losses" not in {row.metric_id for row in rows}
