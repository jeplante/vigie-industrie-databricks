from __future__ import annotations

import json
from pathlib import Path

import pytest

from vigie_databricks.insurer_contract import (
    load_insurer_contract,
    parse_finance_observation_candidate,
    parse_period_id,
)


ROOT = Path(__file__).resolve().parents[1]


def test_insurer_contract_loads_the_four_target_companies_and_sources() -> None:
    contract = load_insurer_contract(ROOT / "config")
    assert contract.finance_policy.raw_content_retention_days == 365
    assert contract.finance_policy.raw_content_volume == "/Volumes/workspace/vigie/finance_raw"
    assert contract.finance_policy.ai_provider == "databricks_model_serving"
    assert contract.finance_policy.publication_destination == "databricks_app"
    assert contract.finance_policy.live_network_enabled_by_default is False

    assert set(contract.companies) == {"MFC", "SLF", "GWO", "IAG"}
    assert set(contract.financial_sources) == set(contract.companies)
    assert contract.companies["MFC"].ticker == "MFC.TO"
    assert contract.financial_sources["IAG"].allowed_hosts == ("ia.ca",)
    assert contract.metrics["licat_ratio"].unit == "PERCENT"


@pytest.mark.parametrize(
    ("period_id", "year", "period_key"),
    [("2026-Q1", 2026, "Q1"), ("2026-Q4", 2026, "Q4"), ("2026-AN", 2026, "AN")],
)
def test_period_id_uses_a_stable_composite_identifier(period_id: str, year: int, period_key: str) -> None:
    parsed = parse_period_id(period_id)

    assert (parsed.year, parsed.period_key) == (year, period_key)


@pytest.mark.parametrize("period_id", ["2026Q1", "2026-Q5", "Q1-2026", "2026-T1"])
def test_period_id_rejects_ambiguous_or_unsupported_formats(period_id: str) -> None:
    with pytest.raises(ValueError, match="period_id"):
        parse_period_id(period_id)


def test_contract_rejects_a_source_url_outside_its_allowlist(tmp_path: Path) -> None:
    (tmp_path / "companies.yaml").write_text(
        "companies:\n  MFC:\n    name: Manuvie\n    full_name: Manuvie\n    ticker: MFC.TO\n    investor_relations_url: https://www.manulife.com/results\n",
        encoding="utf-8",
    )
    (tmp_path / "metrics.yaml").write_text(
        "metrics:\n  net_income:\n    label: Resultat net\n    unit: CAD_BILLION\n    comparison: percent\n    favorable_trend: up\n",
        encoding="utf-8",
    )
    (tmp_path / "sources.yaml").write_text(
        "financial_documents:\n  MFC:\n    source_id: mfc_results\n    url: https://untrusted.example/results\n    allowed_hosts: [www.manulife.com]\n    document_types: [quarterly_report]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allowed_hosts"):
        load_insurer_contract(tmp_path)


def test_slice10_fixture_uses_the_versioned_domain_identifiers() -> None:
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "slice10_insurer_observations.json").read_text(encoding="utf-8")
    )
    contract = load_insurer_contract(ROOT / "config")

    candidates = [parse_finance_observation_candidate(row, contract) for row in fixture]

    assert {candidate.company_id for candidate in candidates} == {"MFC", "SLF", "GWO", "IAG"}
    assert {candidate.period_id for candidate in candidates} >= {"2025-Q4", "2026-Q1", "2026-AN"}


def test_candidate_rejects_an_incorrect_configured_unit() -> None:
    contract = load_insurer_contract(ROOT / "config")
    candidate = {
        "observation_id": "MFC-2026-Q1-core_earnings",
        "company_id": "MFC",
        "metric_id": "core_earnings",
        "period_id": "2026-Q1",
        "value": 1.8,
        "unit": "PERCENT",
        "source_url": "https://www.manulife.com/ca/en/about-us/investors/results-and-reports",
        "source_document_hash": "fixture-hash",
        "quality_status": "candidate",
    }

    with pytest.raises(ValueError, match="unit"):
        parse_finance_observation_candidate(candidate, contract)
