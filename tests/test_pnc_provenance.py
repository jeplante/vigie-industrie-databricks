from pathlib import Path

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_provenance import validate_pnc_source_basis


ROOT = Path(__file__).resolve().parents[1]


def test_td_rejects_combined_wealth_management_and_insurance_context():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    valid, reason = validate_pnc_source_basis(
        "TD",
        "https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2026/q2/2026-q2-report-shareholders-en.pdf",
        "Wealth Management and Insurance net income was $837 million.",
        contract,
    )
    assert not valid
    assert reason == "pnc_disclosure_scope_prohibited"


def test_td_accepts_standalone_insurance_context_on_an_allowlisted_source():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    assert validate_pnc_source_basis(
        "TD",
        "https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2026/q2/2026-q2-report-shareholders-en.pdf",
        "Insurance net income was $279 million.",
        contract,
    ) == (True, None)


def test_av_requires_canada_specific_context():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    assert validate_pnc_source_basis(
        "AV", "https://www.aviva.com/investors/results-reports-and-presentations/", "Group combined ratio was 94.1%.", contract
    ) == (False, "pnc_disclosure_scope_missing")
