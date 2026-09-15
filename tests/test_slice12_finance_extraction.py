from pathlib import Path

import pytest

from vigie_databricks.finance_extraction import extract_finance_metrics, infer_reporting_period
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


def test_manulife_extraction_keeps_context_and_normalizes_metrics():
    content = "<p>Core EPS ($) $1.16. Core earnings $2,000. Core ROE of 18.1%. LICAT ratio of 138%.</p>"
    rows = extract_finance_metrics("MFC", content, load_insurer_contract(ROOT / "config"))
    values = {row.metric_id: row.value for row in rows}
    assert values == {"core_eps": 1.16, "core_earnings": 2.0, "core_roe": 18.1, "licat_ratio": 138.0}
    assert "Core EPS" in rows[0].context


def test_sun_life_and_iag_extract_their_source_specific_metrics():
    contract = load_insurer_contract(ROOT / "config")
    slf = extract_finance_metrics("SLF", "Underlying EPS of $1.89. Underlying net income of $1,050 million. LICAT ratio of 143%.", contract)
    iag = extract_finance_metrics("IAG", "Core EPS of $2.91. Solvency ratio of 132%. Assets under administration of $250 billion.", contract)
    assert {row.metric_id: row.value for row in slf}["core_earnings"] == 1.05
    assert {row.metric_id: row.value for row in iag}["assets_under_administration"] == 250.0


def test_skips_incompatible_earlier_alias_occurrence_and_uses_later_value():
    contract = load_insurer_contract(ROOT / "config")
    rows = extract_finance_metrics("IAG", "Core EPS of $3.68. Core earnings per share of $3.68. Core earnings of $330 million.", contract)
    values = {row.metric_id: row.value for row in rows}
    assert values["core_eps"] == 3.68
    assert values["core_earnings"] == 0.33


def test_skips_core_earnings_adjustments_and_accepts_long_form_eps_alias():
    contract = load_insurer_contract(ROOT / "config")
    iag = extract_finance_metrics(
        "IAG",
        "Core earnings adjustments totalled $3 million. Core earnings were $327 million.",
        contract,
    )
    slf = extract_finance_metrics("SLF", "Underlying earnings per share of $1.79.", contract)
    assert {row.metric_id: row.value for row in iag}["core_earnings"] == 0.327
    assert {row.metric_id: row.value for row in slf}["core_eps"] == 1.79


def test_extracts_values_from_tables_with_units_in_headers():
    contract = load_insurer_contract(ROOT / "config")
    iag = extract_finance_metrics(
        "IAG",
        "Core earnings (in millions) 327 267. Assets under management and assets under administration (in billions)7 $273.8 $264.0.",
        contract,
    )
    slf = extract_finance_metrics("SLF", "Underlying EPS ($) (1)(4) 1.79 1.72.", contract)
    assert {row.metric_id: row.value for row in iag} == {"core_earnings": 0.327, "assets_under_administration": 273.8}
    assert {row.metric_id: row.value for row in slf} == {"core_eps": 1.79}


def test_skips_percentage_change_and_year_headers_before_reported_values():
    contract = load_insurer_contract(ROOT / "config")
    gwo = extract_finance_metrics(
        "GWO",
        "LICAT Ratio increased by 2%. Later, the LICAT Ratio was 128%.",
        contract,
    )
    iag = extract_finance_metrics(
        "IAG",
        "Net income attributed to common shareholders (in millions) Second quarter Year-to-date at June 30 2024 2023 2024 2023 $206 $196.",
        contract,
    )
    assert {row.metric_id: row.value for row in gwo}["licat_ratio"] == 128.0
    assert {row.metric_id: row.value for row in iag}["net_income"] == pytest.approx(0.206)


def test_repairs_split_percent_and_extracts_older_gwo_labels():
    contract = load_insurer_contract(ROOT / "config")
    slf = extract_finance_metrics("SLF", "LICAT ratios at period end Sun Life Financial Inc. 1 29%.", contract)
    gwo = extract_finance_metrics(
        "GWO",
        "Lifeco base earnings $808 million. Lifeco net earnings - common shareholders $595 million. Base earnings per common share $0.87. Base return on equity 14.7%. Empower assets under administration (AUA) were $1.4 trillion. Total assets under administration (AUA) increased by $127.7 billion to $2.6 trillion.",
        contract,
    )
    values = {row.metric_id: row.value for row in gwo}
    assert {row.metric_id: row.value for row in slf}["licat_ratio"] == 129.0
    assert values["core_earnings"] == 0.808
    assert values["net_income"] == 0.595
    assert values["core_eps"] == 0.87
    assert values["core_roe"] == 14.7
    assert values["total_client_assets"] == 2.6


def test_reporting_period_inference_requires_an_explicit_year_and_period_marker():
    assert infer_reporting_period("Sun Life reports first quarter 2026 results") == "2026-Q1"
    assert infer_reporting_period("Great-West Lifeco full year 2025 results") == "2025-AN"
    assert infer_reporting_period("pa-e-q226-earnings.pdf") == "2026-Q2"
    assert infer_reporting_period("Manulife 2Q26 results") == "2026-Q2"
    assert infer_reporting_period("Quarterly results") is None


def test_gwo_extraction_does_not_treat_inline_reference_markers_as_values():
    content = """
    Base earnings1 $ 1,270 $ 1,149. Net earnings $ 1,039 $ 894.
    Base EPS2 $ 1.42 $ 1.24. Base ROE2,3 19.3 % 17.4 %.
    """

    rows = extract_finance_metrics("GWO", content, load_insurer_contract(ROOT / "config"))

    assert {row.metric_id: row.value for row in rows} == {
        "core_eps": 1.42,
        "core_earnings": 1.27,
        "net_income": 1.039,
        "core_roe": 19.3,
    }


def test_gwo_q4_assets_table_without_explicit_scale_is_interpreted_as_millions():
    rows = extract_finance_metrics(
        "GWO",
        "Total assets under administration1,4  2,497,712  2,384,273  2,291,592",
        load_insurer_contract(ROOT / "config"),
    )
    assert {row.metric_id: row.value for row in rows}["total_client_assets"] == pytest.approx(2.497712)
