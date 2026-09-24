from pathlib import Path

import pytest
import yaml

from vigie_databricks.finance_acquisition import FinancialDocumentFetch
from vigie_databricks.finance_documents import create_financial_document
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_live import acquire_pnc_documents


ROOT = Path(__file__).resolve().parents[1]


def inputs():
    return (load_insurer_contract(ROOT / "config/pnc"),
            yaml.safe_load((ROOT / "tests/fixtures/pnc_source_manifest.yaml").read_text())["sources"])


def test_acquisition_keeps_candidates_in_review_and_isolates_failure():
    contract, manifest = inputs()
    calls = []

    def fetch(contract, company, kind, url, **kwargs):
        calls.append(company)
        if company == "AV":
            raise TimeoutError("private response body")
        content = b"Insurance net income was $279 million."
        document = create_financial_document(contract, company, kind, url, "fetched",
                                             content=content, content_type="text/html")
        return FinancialDocumentFetch(document, content)

    result = acquire_pnc_documents(contract, manifest, document_fetcher=fetch,
                                   text_extractor=lambda content, kind: content.decode())
    assert len(calls) == 4
    assert len(result.documents) == 3
    assert result.errors == {"AV": "TimeoutError"}
    assert result.candidates
    assert all(row["validation_status"] == "needs_period_and_accounting_basis_review" for row in result.candidates)


def test_invalid_manifest_fails_before_network():
    contract, manifest = inputs()
    manifest[0]["source_url"] = "https://unapproved.example/report.pdf"
    def fetch(*args, **kwargs):
        pytest.fail("network must not run")
    with pytest.raises(ValueError, match="approved"):
        acquire_pnc_documents(contract, manifest, document_fetcher=fetch)


def test_explicitly_unavailable_quarterly_source_is_not_fetched_or_extracted():
    contract = load_insurer_contract(ROOT / "config/pnc")
    manifest = yaml.safe_load((ROOT / "config/pnc/history/2025-Q4.yaml").read_text())["sources"]
    calls = []

    def fetch(contract, company, kind, url, **kwargs):
        calls.append(company)
        content = b"Insurance net income was $142 million."
        document = create_financial_document(contract, company, kind, url, "fetched",
                                             content=content, content_type="text/html")
        return FinancialDocumentFetch(document, content)

    result = acquire_pnc_documents(contract, manifest, document_fetcher=fetch,
                                   text_extractor=lambda content, kind: content.decode())
    assert calls == ["IFC", "TD", "DFY"]
    assert len(result.documents) == 3
    assert result.errors == {}
    assert all(row["company_id"] != "AV" for row in result.candidates)


def test_unavailable_source_cannot_hide_an_acquisition_url():
    contract = load_insurer_contract(ROOT / "config/pnc")
    manifest = yaml.safe_load((ROOT / "config/pnc/history/2025-Q4.yaml").read_text())["sources"]
    manifest[1]["source_url"] = "https://www.aviva.com/annual-report"
    with pytest.raises(ValueError, match="cannot have an acquisition URL"):
        acquire_pnc_documents(contract, manifest)
