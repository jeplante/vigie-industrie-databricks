from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError

import pytest

from vigie_databricks.finance_acquisition import acquire_financial_document
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


class FakeHeaders:
    def __init__(self, content_type: str, etag: str | None = None):
        self.content_type = content_type
        self.etag = etag

    def get_content_type(self) -> str:
        return self.content_type

    def get(self, key: str, default=None):
        return self.etag if key == "ETag" else default


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/pdf", etag: str | None = None):
        self.payload = payload
        self.headers = FakeHeaders(content_type, etag)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


def test_finance_acquisition_is_bounded_and_sends_conditional_headers(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse(b"%PDF official report", etag='"current"')

    monkeypatch.setattr("vigie_databricks.finance_acquisition.urlopen", fake_urlopen)
    result = acquire_financial_document(
        load_insurer_contract(ROOT / "config"),
        "MFC",
        "quarterly_report",
        "https://www.manulife.com/ca/en/about-us/investors/results-and-reports/q1.pdf",
        etag='"prior"',
        last_modified="Thu, 03 Sep 2026 12:00:00 GMT",
    )

    request, timeout = requests[0]
    assert timeout == 20
    assert request.get_header("If-none-match") == '"prior"'
    assert request.get_header("If-modified-since") == "Thu, 03 Sep 2026 12:00:00 GMT"
    assert result.document.acquisition_status == "fetched"
    assert result.content == b"%PDF official report"


def test_finance_acquisition_marks_a_304_response_unchanged(monkeypatch) -> None:
    def unchanged(request, timeout):
        raise HTTPError(request.full_url, 304, "Not Modified", {}, None)

    monkeypatch.setattr("vigie_databricks.finance_acquisition.urlopen", unchanged)
    result = acquire_financial_document(
        load_insurer_contract(ROOT / "config"),
        "SLF",
        "quarterly_report",
        "https://www.sunlife.com/en/investors/financial-results-and-reports/quarterly-reports/q1.pdf",
        known_content_hash="a" * 64,
        etag='"prior"',
    )

    assert result.content is None
    assert result.document.acquisition_status == "unchanged"
    assert result.document.content_hash == "a" * 64


def test_finance_acquisition_rejects_unexpected_content_type(monkeypatch) -> None:
    monkeypatch.setattr(
        "vigie_databricks.finance_acquisition.urlopen",
        lambda request, timeout: FakeResponse(b"<html>", "application/octet-stream"),
    )

    with pytest.raises(ValueError, match="content type"):
        acquire_financial_document(
            load_insurer_contract(ROOT / "config"),
            "IAG",
            "annual_report",
            "https://ia.ca/a-propos/investisseurs/rapports-financiers/report.pdf",
        )