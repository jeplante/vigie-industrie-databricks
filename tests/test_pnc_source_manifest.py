from pathlib import Path
from urllib.parse import urlparse

import yaml

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.finance_documents import _validate_source_url
from vigie_databricks.pnc_provenance import PNC_SOURCE_BASIS


ROOT = Path(__file__).resolve().parents[1]


def test_official_pnc_source_manifest_covers_each_configured_company():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    manifest = yaml.safe_load((ROOT / "tests" / "fixtures" / "pnc_source_manifest.yaml").read_text(encoding="utf-8"))
    sources = manifest["sources"]
    assert {source["company_id"] for source in sources} == set(contract.companies)
    for source in sources:
        company_id = source["company_id"]
        assert source["fixture_status"] == "official_source_confirmed"
        assert source["document_type"] == "quarterly_report"
        assert urlparse(source["source_url"]).hostname in contract.financial_sources[company_id].allowed_hosts
        assert source["disclosure_scope"] == PNC_SOURCE_BASIS[company_id].disclosure_scope


def test_historical_q1_manifest_is_bounded_to_official_issuer_hosts():
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    manifest = yaml.safe_load((ROOT / "config" / "pnc" / "history" / "2026-Q1.yaml").read_text(encoding="utf-8"))
    sources = manifest["sources"]
    assert len(sources) == len(contract.companies)
    assert {source["company_id"] for source in sources} == set(contract.companies)
    for source in sources:
        assert source["period_id"] == "2026-Q1"
        assert source["document_type"] == "quarterly_report"
        _validate_source_url(contract.financial_sources[source["company_id"]], source["source_url"])
