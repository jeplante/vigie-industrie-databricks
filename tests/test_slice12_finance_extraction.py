from pathlib import Path

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
