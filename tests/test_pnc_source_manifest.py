from pathlib import Path
from urllib.parse import urlparse

import yaml

from vigie_databricks.insurer_contract import load_insurer_contract
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
