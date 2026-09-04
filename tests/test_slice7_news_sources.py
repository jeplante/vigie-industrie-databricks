from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest

from vigie_databricks.news_bronze import (
    NewsSource,
    acquire_feed,
    acquire_sources,
    parse_feed,
    parse_sources_json,
    validate_live_url,
)


class FakeHeaders:
    def __init__(self, content_type: str):
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/atom+xml"):
        self.payload = payload
        self.headers = FakeHeaders(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


def test_atom_contract_and_timestamp_normalization():
    payload = Path("tests/fixtures/slice7_statcan_atom.xml").read_bytes()
    rows = parse_feed(payload, "statcan_manufacturing")
    assert len(rows) == 2
    assert rows[0]["source"] == "statcan_manufacturing"
    assert rows[0]["published_at_iso"] == "2026-08-27T12:30:00+00:00"
    assert rows[0]["source_url"].endswith("utm_source=feed")
    assert "Manufacturing sales" in rows[0]["title_raw"]
    assert len({row["article_id"] for row in rows}) == 2


def test_source_configuration_is_strict():
    config = json.dumps([
        {"source_id": "statcan_manufacturing", "url": "https://www150.statcan.gc.ca/n1/rss/dai-quo/16-eng.atom"},
        {"source_id": "statcan_trade", "url": "https://www150.statcan.gc.ca/n1/rss/dai-quo/12-eng.atom", "enabled": False},
    ])
    sources = parse_sources_json(config)
    assert sources[0].enabled is True
    assert sources[1].enabled is False

    with pytest.raises(ValueError, match="approved host"):
        validate_live_url("https://example.com/feed.xml")
    with pytest.raises(ValueError, match="Duplicate"):
        parse_sources_json(json.dumps([
            {"source_id": "same", "url": "https://www150.statcan.gc.ca/a.atom"},
            {"source_id": "same", "url": "https://www150.statcan.gc.ca/b.atom"},
        ]))
    with pytest.raises(ValueError, match="only source_id"):
        parse_sources_json(json.dumps([
            {"source_id": "one", "url": "https://www150.statcan.gc.ca/a.atom", "unexpected": 1},
        ]))


def test_acquisition_enforces_type_size_and_limit(monkeypatch):
    payload = Path("tests/fixtures/slice7_statcan_atom.xml").read_bytes()
    monkeypatch.setattr("vigie_databricks.news_bronze.urlopen", lambda request, timeout: FakeResponse(payload))
    rows = acquire_feed(
        "https://www150.statcan.gc.ca/n1/rss/dai-quo/16-eng.atom",
        "statcan_manufacturing",
        max_articles=1,
    )
    assert len(rows) == 1

    monkeypatch.setattr(
        "vigie_databricks.news_bronze.urlopen",
        lambda request, timeout: FakeResponse(payload, "text/html"),
    )
    with pytest.raises(ValueError, match="content type"):
        acquire_feed("https://www150.statcan.gc.ca/a.atom", "source")

    monkeypatch.setattr(
        "vigie_databricks.news_bronze.urlopen",
        lambda request, timeout: FakeResponse(b"x" * 101),
    )
    with pytest.raises(ValueError, match="size limit"):
        acquire_feed("https://www150.statcan.gc.ca/a.atom", "source", max_response_bytes=100)


def test_multi_source_failure_is_isolated(monkeypatch):
    payload = Path("tests/fixtures/slice7_statcan_atom.xml").read_bytes()

    def fake_acquire(url, source, max_articles=25, **kwargs):
        if source == "failed":
            raise URLError("temporary failure")
        return parse_feed(payload, source)[:max_articles]

    monkeypatch.setattr("vigie_databricks.news_bronze.acquire_feed", fake_acquire)
    rows, succeeded, failed = acquire_sources([
        NewsSource("working", "https://www150.statcan.gc.ca/working.atom"),
        NewsSource("failed", "https://www150.statcan.gc.ca/failed.atom"),
    ])
    assert len(rows) == 2
    assert succeeded == 1
    assert failed == 1

    with pytest.raises(ValueError, match="All enabled"):
        acquire_sources([NewsSource("failed", "https://www150.statcan.gc.ca/failed.atom")])


def test_job_template_has_approved_sources_and_active_schedule():
    template = json.loads(Path("databricks_slice6_news_job.template.json").read_text(encoding="utf-8"))
    parameters = {item["name"]: item["default"] for item in template["parameters"]}
    sources = json.loads(parameters["sources_json"])
    assert [source["source_id"] for source in sources] == [
        "statcan_manufacturing",
        "statcan_international_trade",
    ]
    assert parameters["source_mode"] == "live"
    assert parameters["max_articles"] == "25"
    assert template["schedule"] == {
        "quartz_cron_expression": "0 0 0/6 * * ?",
        "timezone_id": "America/Toronto",
        "pause_status": "UNPAUSED",
    }
