from __future__ import annotations

from pathlib import Path

from vigie_databricks.finance_documents import create_financial_document
from datetime import UTC, datetime

from vigie_databricks.finance_live import acquire_live_finance, discover_mfc_direct_documents, persist_raw_content
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


def test_live_finance_selects_latest_report_and_builds_deterministic_candidates(tmp_path):
    contract = load_insurer_contract(ROOT / "config")
    pages = {
        company_id: '<a href="/reports/2025-q4.pdf">Q4 2025 report</a><a href="/reports/2026-q1.pdf">Q1 2026 report</a>'
        for company_id in contract.companies
    }

    def page_fetcher(source):
        return pages[source.company_id]

    def document_fetcher(contract, company_id, document_type, source_url, **kwargs):
        from vigie_databricks.finance_acquisition import FinancialDocumentFetch
        payload = b"<p>Core EPS $1.25. Core earnings $2,000 million. Underlying EPS $1.25. Underlying net income $2,000 million. Base EPS $1.25. Base earnings $2,000 million. LICAT ratio 140%. Solvency ratio 140%.</p>"
        document = create_financial_document(contract, company_id, document_type, source_url, "fetched", content=payload, content_type="text/html")
        return FinancialDocumentFetch(document, payload)

    result = acquire_live_finance(contract, {}, persist_raw=False, page_fetcher=page_fetcher, document_fetcher=document_fetcher)

    assert result.sources_succeeded == 4
    assert result.documents_fetched == 4
    assert {candidate["period_id"] for candidate in result.candidates if candidate["company_id"] != "MFC"} == {"2026-Q1"}
    assert {candidate["company_id"] for candidate in result.candidates} == set(contract.companies)


def test_live_finance_isolates_one_failed_source():
    contract = load_insurer_contract(ROOT / "config")

    def page_fetcher(source):
        if source.company_id == "SLF":
            raise TimeoutError("secret details must not leak")
        return "<p>No reports</p>"

    def document_fetcher(*args, **kwargs):
        raise TimeoutError("unavailable")

    result = acquire_live_finance(contract, {}, persist_raw=False, page_fetcher=page_fetcher, document_fetcher=document_fetcher)

    assert result.sources_succeeded == 0
    assert result.source_errors["SLF"] == "timeouterror_secret_details_must_not_leak"
    assert len(result.documents) == 4
    assert all(document.acquisition_status == "failed" for document in result.documents)


def test_mfc_direct_discovery_is_bounded_newest_first():
    documents = discover_mfc_direct_documents(datetime(2026, 9, 5, tzinfo=UTC), max_quarters=3)
    assert [item.source_url.rsplit("/", 1)[-1] for item in documents] == [
        "MFC_SR_2026_Q3_EN.pdf", "MFC_SR_2026_Q2_EN.pdf", "MFC_SR_2026_Q1_EN.pdf",
    ]


def test_raw_content_persistence_is_content_addressed_and_idempotent(tmp_path):
    contract = load_insurer_contract(ROOT / "config")
    payload = b"%PDF deterministic"
    document = create_financial_document(contract, "MFC", "quarterly_report", "https://www.manulife.com/reports/2026-q1.pdf", "fetched", content=payload, content_type="application/pdf")

    first = persist_raw_content(str(tmp_path), document, payload)
    second = persist_raw_content(str(tmp_path), document, payload)

    assert first.raw_content_path == second.raw_content_path
    assert Path(first.raw_content_path).read_bytes() == payload
