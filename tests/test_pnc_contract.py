from pathlib import Path

from vigie_databricks.insurer_contract import load_insurer_contract


def test_pnc_contract_is_complete_and_separate_from_life_domain():
    contract = load_insurer_contract(Path(__file__).resolve().parents[1] / "config" / "pnc")
    assert set(contract.companies) == {"IFC", "AV", "TD", "DFY"}
    assert set(contract.financial_sources) == set(contract.companies)
    assert contract.finance_policy.raw_content_volume.endswith("/pnc_finance_raw")
    assert {"combined_ratio", "claims_ratio", "operating_income"} <= set(contract.metrics)
