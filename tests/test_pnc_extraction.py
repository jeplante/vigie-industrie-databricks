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


def test_ifc_candidates_are_deterministic_and_unit_normalized():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    rows = extract_pnc_metrics(
        "IFC",
        "Insurance revenue was $6,240 million. Combined ratio was 91.2%. Operating net income was $820 million. Operating ROE was 16.4%.",
        contract,
    )
    values = {row.metric_id: row.value for row in rows}
    assert values["insurance_revenue"] == pytest.approx(6.24)
    assert values["combined_ratio"] == pytest.approx(91.2)
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
        "<h2>Per share measures</h2>"
    )
    rows = extract_pnc_metrics("IFC", report, contract)
    net_income = next(row for row in rows if row.metric_id == "net_income")
    assert net_income.value == pytest.approx(0.720)
    assert "Q2-2026" in net_income.context


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
