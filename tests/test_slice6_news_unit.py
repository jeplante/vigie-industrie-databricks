from __future__ import annotations

import json
from pathlib import Path

import pytest

from vigie_databricks.news_ai import PROMPT_VERSION, build_prompt, enrichment_input_hash, parse_output
from vigie_databricks.news_bronze import article_id, content_hash, normalize_url, parse_rss


def test_rss_contract_and_stable_identity():
    payload = Path("tests/fixtures/slice6_news_rss.xml").read_bytes()
    rows = parse_rss(payload, "rss_fixture")
    assert len(rows) == 2
    assert rows[0]["article_id"] == article_id("rss_fixture", "slice6-news-1", rows[0]["source_url"])
    assert rows[0]["source_url"].endswith("utm_source=fixture")
    assert normalize_url("https://EXAMPLE.test/a/?utm_source=x#f") == "https://example.test/a"
    assert content_hash("A  title", "A description", "https://example.test/a") == content_hash("A title", "A description", "https://example.test/a")


def test_ai_parser_is_strict_and_bounded():
    value = parse_output(json.dumps({"summary": "ok", "categories": ["strategy"], "relevant_company_ids": []}), {"C1"})
    assert value["relevant_company_ids"] == []
    with pytest.raises(ValueError):
        parse_output('{"summary":"ok","categories":["unknown"],"relevant_company_ids":[]}', set())
    with pytest.raises(ValueError):
        parse_output('{"summary":"ok","categories":["strategy"],"relevant_company_ids":[],"score":1}', set())


def test_ai_hash_excludes_model_and_prompt_configuration():
    row = {"article_id": "a1", "content_hash": "content-1", "title": "Title", "description": "Desc", "source_url": "https://example.test"}
    assert enrichment_input_hash(row) == enrichment_input_hash({**row, "model_name": "other", "prompt_version": "other"})
    assert PROMPT_VERSION in build_prompt(row) or "instruction" in build_prompt(row)