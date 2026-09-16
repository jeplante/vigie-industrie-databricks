from pathlib import Path

import pytest

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import extract_pnc_metrics


ROOT = Path(__file__).resolve().parents[1]


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


def test_td_extracts_only_explicit_insurance_values():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    rows = extract_pnc_metrics(
        "TD",
        "Wealth Management and Insurance net income was $837 million. Insurance net income was $279 million. Return on common equity – Insurance was 35.9%.",
        contract,
    )
    assert {row.metric_id: row.value for row in rows} == {"net_income": 0.279, "operating_roe": 35.9}
