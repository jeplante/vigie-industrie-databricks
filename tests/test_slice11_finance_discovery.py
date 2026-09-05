from __future__ import annotations

from pathlib import Path

from vigie_databricks.finance_discovery import discover_financial_documents
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


def test_discovery_returns_only_approved_classified_pdf_links() -> None:
    source = load_insurer_contract(ROOT / "config").financial_sources["MFC"]
    html = """
    <a href="/reports/2026-q1.pdf">2026 Q1 financial results</a>
    <a href="https://www.manulife.com/reports/2025-annual.pdf">2025 annual report</a>
    <a href="https://example.com/q2.pdf">Q2 report</a>
    <a href="/reports/news.html">Quarterly news</a>
    <a href="/reports/notes.pdf">Investor notes</a>
    """

    documents = discover_financial_documents(html, source)

    assert [(item.document_type, item.source_url) for item in documents] == [
        ("annual_report", "https://www.manulife.com/reports/2025-annual.pdf"),
        ("quarterly_report", "https://www.manulife.com/reports/2026-q1.pdf"),
    ]


def test_discovery_deduplicates_links_deterministically() -> None:
    source = load_insurer_contract(ROOT / "config").financial_sources["GWO"]
    html = '<a href="/reports/q1.pdf">Quarterly report</a><a href="/reports/q1.pdf">Q1 report</a>'

    documents = discover_financial_documents(html, source)

    assert len(documents) == 1
    assert documents[0].document_type == "quarterly_report"


def test_discovery_accepts_compact_quarter_year_in_official_filename() -> None:
    source = load_insurer_contract(ROOT / "config").financial_sources["SLF"]
    documents = discover_financial_documents('<a href="/reports/pa-e-q226-shrpt.pdf">Report to shareholders</a>', source)
    assert documents[0].document_type == "quarterly_report"
