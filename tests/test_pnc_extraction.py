from pathlib import Path

import pytest

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import extract_pnc_metrics


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("content", [
    "Insurance revenue unavailable. Combined ratio was 91.2%.",
    "Insurance revenue declined by 5%.",
    "Insurance revenue was GBP 100 million.",
])
def test_does_not_invent_revenue_from_neighboring_or_incompatible_values(content):
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    assert "insurance_revenue" not in {row.metric_id for row in extract_pnc_metrics("IFC", content, contract)}


def test_operating_income_is_not_net_income():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    rows = extract_pnc_metrics("IFC", "Operating net income was $820 million. Return on equity was 17%.", contract)
    assert {row.metric_id for row in rows} == {"operating_income"}


def test_cumulative_definity_values_are_not_quarterly_candidates():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    text = (
        "Year to date, operating net income was $236.1 million. "
        "Year to date, net income attributable to common shareholders was $216.3 million."
    )
    assert extract_pnc_metrics("DFY", text, contract) == []


def test_visible_quarterly_html_values_precede_cumulative_values():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    text = (
        '<html><head><script>Operating net income was $999 million.</script></head><body>'
        '<li><span>Operating net income</span> was $118.0 million in Q2 2026. '
        'Year to date, operating net income was $236.1 million.</li>'
        '<li><span>Net income attributable to common shareholders</span> was $152.4 million in Q2 2026.</li>'
        '</body></html>'
    )
    values = {row.metric_id: row.value for row in extract_pnc_metrics("DFY", text, contract)}
    assert values["operating_income"] == pytest.approx(.118)
    assert values["net_income"] == pytest.approx(.1524)


def test_definity_revenue_requires_quarterly_cad_millions_table():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    report = (
        "<h2>Consolidated Results</h2>"
        "<p>(in millions of dollars, except as otherwise noted)</p>"
        "<tr><td>Q3 2025</td><td>Q3 2024</td><td>Change</td>"
        "<td>2025 YTD</td><td>2024 YTD</td></tr>"
        "<tr><td>Insurance revenue</td><td>1,183.6</td><td>1,095.5</td>"
        "<td>3,457.6</td></tr><h2>Per share measures</h2>"
    )
    rows = extract_pnc_metrics("DFY", report, contract)
    revenue = next(row for row in rows if row.metric_id == "insurance_revenue")
    assert revenue.value == pytest.approx(1.1836)
    assert "Q3 2025" in revenue.context
    assert "3,457.6" not in revenue.context
    assert "insurance_revenue" not in {
        row.metric_id for row in extract_pnc_metrics(
            "DFY", "Consolidated Results (in millions of dollars) 2025 YTD "
            "Insurance revenue 3,457.6. Per share measures", contract
        )
    }


def test_ifc_candidates_are_deterministic_and_unit_normalized():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    rows = extract_pnc_metrics(
        "IFC",
        "Insurance revenue was $6,240 million. Combined ratio was 91.2%. Operating net income was $820 million. Operating ROE was 16.4%.",
        contract,
    )
    values = {row.metric_id: row.value for row in rows}
    assert values["insurance_revenue"] == pytest.approx(6.24)
    assert "combined_ratio" not in values  # No table proves consolidated scope.
    assert values["operating_income"] == pytest.approx(0.82)
    assert values["operating_roe"] == pytest.approx(16.4)


def test_ifc_highlights_net_income_uses_quarterly_first_column():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    report = (
        "<h2>Consolidated Highlights</h2>"
        "<p>(in millions of Canadian dollars except as otherwise noted)</p>"
        "<tr><td>Q2-2026</td><td>Q2-2025</td><td>Change</td>"
        "<td>H1-2026</td><td>H1-2025</td></tr>"
        "<tr><td>Net operating income attributable to common shareholders</td>"
        "<td>561</td><td>935</td><td>1,331</td></tr>"
        "<tr><td>Net income</td><td>720</td><td>867</td><td>1,472</td></tr>"
        "<tr><td>Combined Ratio</td><td>94.9 %</td><td>91.0 %</td></tr>"
        "<h2>Per share measures</h2>"
    )
    rows = extract_pnc_metrics("IFC", report, contract)
    net_income = next(row for row in rows if row.metric_id == "net_income")
    operating_income = next(row for row in rows if row.metric_id == "operating_income")
    assert net_income.value == pytest.approx(0.720)
    assert operating_income.value == pytest.approx(0.561)
    assert next(row for row in rows if row.metric_id == "combined_ratio").value == pytest.approx(94.9)
    assert "Q2-2026" in net_income.context
    assert "common shareholders" in operating_income.context


def test_ifc_segment_ratio_cannot_replace_consolidated_ratio():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    report = (
        "<h2>Consolidated Highlights</h2>"
        "<p>(in millions of Canadian dollars except as otherwise noted)</p>"
        "<tr><td>Q1-2026</td><td>Q1-2025</td><td>Change</td></tr>"
        "<tr><td>Combined Ratio</td><td>91.3 %</td><td>91.3 %</td></tr>"
        "<h2>Per share measures</h2>"
        "<p>Canada personal property combined ratio of 84.4%.</p>"
    )
    ratio = next(row for row in extract_pnc_metrics("IFC", report, contract)
                 if row.metric_id == "combined_ratio")
    assert ratio.value == pytest.approx(91.3)
    assert "Consolidated Highlights Q1-2026" in ratio.context


def test_ifc_pdf_highlights_skip_footnote_markers_not_current_values():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    pdf_text = (
        "Consolidated Highlights\n"
        "(in millions of Canadian dollars except as otherwise noted)\n"
        "Q1-2026\nQ1-2025\nChange\n"
        "Net operating income attributable to common\nshareholders\n1\n770\n717\n7 %\n"
        "Net income\n752\n676\n11 %\n"
        "Combined Ratio\n1\n91.3 %\n91.3 %\n-- pts\n"
        "Per share measures (in dollars)\n"
        "Canada personal property combined ratio of 84.4%."
    )
    values = {row.metric_id: row.value for row in extract_pnc_metrics("IFC", pdf_text, contract)}
    assert values["operating_income"] == pytest.approx(0.770)
    assert values["net_income"] == pytest.approx(0.752)
    assert values["combined_ratio"] == pytest.approx(91.3)


def test_ifc_highlights_requires_cad_millions_and_quarter_header():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    report = (
        "<h2>Consolidated Highlights</h2><p>(in millions of pounds)</p>"
        "<tr><td>H1-2026</td><td>H1-2025</td><td>Change</td></tr>"
        "<tr><td>Net income</td><td>720</td></tr><h2>Per share measures</h2>"
    )
    assert "net_income" not in {row.metric_id for row in extract_pnc_metrics("IFC", report, contract)}


def test_td_extracts_only_explicit_insurance_values():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    rows = extract_pnc_metrics(
        "TD",
        "Wealth Management and Insurance net income was $837 million. Insurance net income was $279 million. Return on common equity – Insurance was 35.9%.",
        contract,
    )
    assert {row.metric_id: row.value for row in rows} == {"net_income": 0.279, "operating_roe": 35.9}


def test_td_quarterly_comparison_extracts_insurance_component_not_bank_segment():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    text = (
        "Quarterly comparison – Q1 2026 vs. Q1 2025 Other bank results. "
        "Quarterly comparison – Q1 2026 vs. Q1 2025 "
        "Wealth Management and Insurance net income for the quarter was $757 million, "
        "reflecting Wealth Management net income of $574 million, an increase, "
        "and Insurance net income of $183 million, an increase. "
        "Quarterly comparison – Q1 2026 vs. Q4 2025 "
        "Insurance net income of $999 million in an unrelated paragraph."
    )
    values = {row.metric_id: row for row in extract_pnc_metrics("TD", text, contract)}
    assert values["net_income"].value == pytest.approx(0.183)
    assert "Q1 2026" in values["net_income"].context


def test_td_combined_segment_only_does_not_generate_insurance_candidate():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    text = (
        "Quarterly comparison – Q1 2026 vs. Q1 2025 "
        "Wealth Management and Insurance net income for the quarter was $757 million."
    )
    assert "net_income" not in {row.metric_id for row in extract_pnc_metrics("TD", text, contract)}


def test_td_layout_quarterly_insurance_excludes_nine_month_comparison():
    contract = load_insurer_contract(ROOT / "config/pnc")
    text = (
        "Quarterly comparison – Q3 2025 vs. Q2 2025 "
        "Wealth Management and Insurance net income for the quarter was $703 million, "
        "reflecting Wealth Management net income of $521 million, "
        "and Insurance net income of $182 million. "
        "Year-to-date comparison – Q3 2025 vs. Q3 2024 "
        "Insurance net income of $577 million."
    )
    rows = {row.metric_id: row for row in extract_pnc_metrics("TD", text, contract)}
    assert rows["net_income"].value == pytest.approx(0.182)
    assert "Q3 2025" in rows["net_income"].context
