from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from vigie_databricks.finance_documents import (
    FINANCIAL_DOCUMENT_SCHEMA,
    FINANCE_RUN_AUDIT_SCHEMA,
    create_financial_document,
)
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


def test_finance_document_contract_captures_source_provenance() -> None:
    contract = load_insurer_contract(ROOT / "config")
    document = create_financial_document(
        contract,
        "MFC",
        "quarterly_report",
        "https://www.manulife.com/ca/en/about-us/investors/results-and-reports/q1.pdf",
        "fetched",
        content=b"official report",
        etag='"v1"',
        content_type="application/pdf",
        fetched_at=datetime(2026, 9, 4, tzinfo=UTC),
    )

    assert document.company_id == "MFC"
    assert document.source_id == "mfc_financial_results"
    assert document.content_length == len(b"official report")
    assert len(document.content_hash) == 64
    assert document.acquisition_status == "fetched"


def test_finance_document_rejects_unapproved_source_host() -> None:
    contract = load_insurer_contract(ROOT / "config")

    with pytest.raises(ValueError, match="not approved"):
        create_financial_document(
            contract,
            "SLF",
            "quarterly_report",
            "https://example.com/report.pdf",
            "discovered",
        )


def test_failed_document_records_a_reason_without_content() -> None:
    contract = load_insurer_contract(ROOT / "config")
    document = create_financial_document(
        contract,
        "GWO",
        "annual_report",
        "https://www.greatwestlifeco.com/news-events/annual-reports.html",
        "failed",
        error_code="source_timeout",
    )

    assert document.content_hash == ""
    assert document.error_code == "source_timeout"


def test_finance_schemas_include_provenance_and_run_counters() -> None:
    assert "source_url string" in FINANCIAL_DOCUMENT_SCHEMA
    assert "content_hash string" in FINANCIAL_DOCUMENT_SCHEMA
    assert "raw_content_path string" in FINANCIAL_DOCUMENT_SCHEMA
    assert "acquisition_status string" in FINANCIAL_DOCUMENT_SCHEMA
    assert "sources_succeeded long" in FINANCE_RUN_AUDIT_SCHEMA
    assert "candidate_observations long" in FINANCE_RUN_AUDIT_SCHEMA
