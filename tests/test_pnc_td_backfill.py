"""TD standalone Insurance net income for 2024, read in the 2025 reports' comparisons (real sentences)."""
from pathlib import Path

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import extract_pnc_metrics

CONTRACT = load_insurer_contract(Path(__file__).resolve().parents[1] / "config/pnc")
WMI = ("Wealth Management and Insurance net income for the quarter was $680 million, an increase of $125 million, or 23%, "
       "compared with the first quarter last year, reflecting Wealth Management net income of $512 million, an increase of "
       "$157 million, or 44%, compared with the first quarter last year, ")
Q1_2025 = (
    "Quarterly comparison – Q1 2025 vs. Q1 2024 " + WMI
    + "and Insurance net income of $168 million , a decrease of $32 million, or 16%, compared with the first quarter last year. "
    "Quarterly comparison – Q1 2025 vs. Q4 2024 Wealth Management and Insurance net income for the quarter was $680 million, "
    "an increase of $331 million, or 95%, compared with the prior quarter, reflecting Wealth Management net income of $512 million, "
    "an increase of $64 million, or 14%, compared with the prior quarter, and Insurance net income of $168 million, an increase "
    "of $267 million, compared with a loss of $99 million in the prior quarter. TABLE 14: OTHER"
)


def values(text, target):
    return [(m.value, m.context) for m in extract_pnc_metrics("TD", text, CONTRACT, target_period=target)]


def test_the_previous_year_quarter_is_derived_and_the_previous_quarter_read_as_written():
    [(value, context)] = values(Q1_2025, "2024-Q1")
    assert value == 0.2 and context.startswith("Q1 2024 Insurance net income of 200 million CAD, derived")
    [(value, context)] = values(Q1_2025, "2024-Q4")
    assert value == -0.099 and "stated in the next quarter's comparison as a loss of $99 million" in context
    assert values(Q1_2025, "2025-Q1")[0][0] == 0.168  # the report's own quarter is unchanged


def test_no_value_for_quarters_the_report_does_not_compare_or_contradicts():
    assert values(Q1_2025, "2023-Q1") == [] and values(Q1_2025, "2024-Q3") == []
    contradiction = Q1_2025.replace("a loss of $99 million", "a loss of $98 million")
    assert values(contradiction, "2024-Q4") == []


def test_derived_values_pass_the_automatic_review_with_a_single_quarter_label():
    from vigie_databricks.pnc_auto_review import review_automatically

    [(value, context)] = values(Q1_2025, "2024-Q4")
    candidate = {"observation_id": "TD-2024-Q4-net_income", "company_id": "TD", "period_id": "2024-Q4", "metric_id": "net_income",
                 "value": value, "unit": "CAD_BILLION", "source_url": "https://www.td.com/x.pdf", "source_document_hash": "a" * 64,
                 "context": context, "validation_status": "needs_period_and_accounting_basis_review"}
    accepted, decisions = review_automatically([candidate], [])
    assert [d["decision"] for d in decisions] == ["accepted"] and accepted[0]["basis_evidence"]["period_end"] == "2024-10-31"
