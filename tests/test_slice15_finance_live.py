from __future__ import annotations

from pathlib import Path

from vigie_databricks.finance_documents import create_financial_document
from datetime import UTC, datetime

from vigie_databricks.finance_discovery import DiscoveredFinancialDocument
from vigie_databricks.finance_live import _latest_document, acquire_live_finance, discover_mfc_direct_documents, persist_raw_content
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
        payload = b"<p>Core EPS $1.25. Core earnings $2,000 million. Net income attributed to shareholders $1,000 million. Core ROE 18%. Underlying EPS $1.25. Underlying net income $2,000 million. Reported net income $1,000 million. Underlying ROE 18%. Assets under management $1,500 billion. Base EPS $1.25. Base earnings $2,000 million. Net earnings $1,000 million. Base ROE 18%. Total client assets $3 trillion. Net income attributed to common shareholders $1,000 million. Assets under administration $300 billion. LICAT ratio 140%. Solvency ratio 140%.</p>"
        document = create_financial_document(contract, company_id, document_type, source_url, "fetched", content=payload, content_type="text/html")
        return FinancialDocumentFetch(document, payload)

    result = acquire_live_finance(contract, {}, persist_raw=False, page_fetcher=page_fetcher, document_fetcher=document_fetcher)

    assert result.sources_succeeded == 4
    assert result.documents_fetched == 4
    assert {candidate["period_id"] for candidate in result.candidates if candidate["company_id"] != "MFC"} == {"2026-Q1"}
    assert {candidate["company_id"] for candidate in result.candidates} == set(contract.companies)


PAYLOAD_WITHOUT_LICAT = b"<p>Core EPS $1.25. Core earnings $2,000 million. Net income attributed to shareholders $1,000 million. Core ROE 18%. Underlying EPS $1.25. Underlying net income $2,000 million. Reported net income $1,000 million. Underlying ROE 18%. Assets under management $1,500 billion. Base EPS $1.25. Base earnings $2,000 million. Net earnings $1,000 million. Base ROE 18%. Total client assets $3 trillion. Net income attributed to common shareholders $1,000 million. Assets under administration $300 billion.</p>"


def _without_licat_fetchers():
    def page_fetcher(source):
        return '<a href="/reports/2026-q1.pdf">Q1 2026 report</a>'

    def document_fetcher(contract, company_id, document_type, source_url, **kwargs):
        from vigie_databricks.finance_acquisition import FinancialDocumentFetch
        document = create_financial_document(contract, company_id, document_type, source_url, "fetched", content=PAYLOAD_WITHOUT_LICAT, content_type="text/html")
        return FinancialDocumentFetch(document, PAYLOAD_WITHOUT_LICAT)

    return page_fetcher, document_fetcher


def test_live_finance_asks_ai_only_for_metrics_missing_from_deterministic_extraction():
    contract = load_insurer_contract(ROOT / "config")
    page_fetcher, document_fetcher = _without_licat_fetchers()
    requests = []

    def ai_fallback(company_id, period_id, source_url, content_hash, text, metric_ids):
        requests.append((company_id, tuple(metric_ids)))
        return [{
            "observation_id": f"{company_id}-{period_id}-{metric_id}", "company_id": company_id,
            "metric_id": metric_id, "period_id": period_id, "value": 140.0,
            "unit": contract.metrics[metric_id].unit, "source_url": source_url,
            "source_document_hash": content_hash, "quality_status": "candidate",
        } for metric_id in metric_ids]

    result = acquire_live_finance(contract, {}, persist_raw=False, page_fetcher=page_fetcher,
                                  document_fetcher=document_fetcher, ai_fallback=ai_fallback)

    assert result.sources_succeeded == 4, result.source_errors
    assert sorted(requests) == [(company_id, ("licat_ratio",)) for company_id in sorted(contract.companies)]
    assert sum(candidate["metric_id"] == "licat_ratio" for candidate in result.candidates) == 4


def test_live_finance_rejects_ai_candidates_for_unrequested_metrics():
    contract = load_insurer_contract(ROOT / "config")
    page_fetcher, document_fetcher = _without_licat_fetchers()

    def ai_fallback(company_id, period_id, source_url, content_hash, text, metric_ids):
        return [{"metric_id": "core_eps"}]

    result = acquire_live_finance(contract, {}, persist_raw=False, page_fetcher=page_fetcher,
                                  document_fetcher=document_fetcher, ai_fallback=ai_fallback)

    assert result.sources_succeeded == 0
    assert set(result.source_errors.values()) == {"valueerror_ai_candidates_outside_requested_metrics"}


FULL_PAYLOAD = PAYLOAD_WITHOUT_LICAT.replace(b"</p>", b" LICAT ratio 140%. Solvency ratio 140%.</p>")


def _unchanged_run(tmp_path, cached_bytes):
    import hashlib
    from vigie_databricks.finance_acquisition import FinancialDocumentFetch

    contract = load_insurer_contract(ROOT / "config")
    content_hash = hashlib.sha256(FULL_PAYLOAD).hexdigest()
    raw_path = tmp_path / "cached.html"
    raw_path.write_bytes(cached_bytes)
    prior = {"content_hash": content_hash, "raw_content_path": str(raw_path), "content_type": "text/html"}

    def document_fetcher(contract, company_id, document_type, source_url, **kwargs):
        document = create_financial_document(contract, company_id, document_type, source_url, "unchanged",
                                             known_content_hash=kwargs["known_content_hash"])
        return FinancialDocumentFetch(document, None)

    class PriorForEveryUrl(dict):
        def get(self, key, default=None):
            return prior

    def page_fetcher(source):
        return '<a href="/reports/2026-q1.pdf">Q1 2026 report</a>'

    prior_by_url = PriorForEveryUrl()
    return acquire_live_finance(contract, prior_by_url, persist_raw=False, page_fetcher=page_fetcher,
                                document_fetcher=document_fetcher)


def test_unchanged_document_reuses_cached_bytes_with_their_content_type(tmp_path):
    result = _unchanged_run(tmp_path, FULL_PAYLOAD)

    assert result.sources_succeeded == 4, result.source_errors
    assert result.documents_unchanged == 4
    assert {document.content_type for document in result.documents} == {"text/html"}


def test_unchanged_document_rejects_cached_bytes_with_a_different_hash(tmp_path):
    result = _unchanged_run(tmp_path, FULL_PAYLOAD + b"tampered")

    assert result.sources_succeeded == 0
    assert set(result.source_errors.values()) == {"valueerror_unchanged_document_hash_mismatch"}


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


def test_latest_document_prefers_shareholder_report_over_transcript_for_same_period():
    selected = _latest_document([
        DiscoveredFinancialDocument("quarterly_report", "https://example.com/q2-2026-transcript.pdf", "Q2 2026 transcript"),
        DiscoveredFinancialDocument("quarterly_report", "https://example.com/pa-e-q226-shrpt.pdf", "Q2 2026 report to shareholders"),
        DiscoveredFinancialDocument("quarterly_report", "https://example.com/q1-2026-report.pdf", "Q1 2026 quarterly report"),
    ])

    assert selected.source_url.endswith("pa-e-q226-shrpt.pdf")


def test_raw_content_persistence_is_content_addressed_and_idempotent(tmp_path):
    contract = load_insurer_contract(ROOT / "config")
    payload = b"%PDF deterministic"
    document = create_financial_document(contract, "MFC", "quarterly_report", "https://www.manulife.com/reports/2026-q1.pdf", "fetched", content=payload, content_type="application/pdf")

    first = persist_raw_content(str(tmp_path), document, payload)
    second = persist_raw_content(str(tmp_path), document, payload)

    assert first.raw_content_path == second.raw_content_path
    assert Path(first.raw_content_path).read_bytes() == payload
