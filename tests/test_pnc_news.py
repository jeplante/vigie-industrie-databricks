from datetime import UTC, datetime
from pathlib import Path

import pytest

from vigie_databricks import pnc_news
from vigie_databricks.pnc_news import (NewsSource, collect_pnc_news, host_allowed, http_get, load_news_sources,
                                       parse_aviva_list, parse_date, parse_rss, parse_td_list)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Q3 catastrophe loss estimate</title><link>https://news.example.com/a</link><description><![CDATA[<p>Estimate &amp; impact</p>]]></description><pubDate>Tue, 06 Oct 2026 17:01:00 -0400</pubDate></item>
<item><title>Board appointment</title><link>https://news.example.com/b</link><description /><pubDate>Wed, 02 Jul 2026 09:00:00 -0400</pubDate></item>
<item><title>Off-host link</title><link>https://evil.example.org/c</link><pubDate>Thu, 01 Oct 2026 09:00:00 -0400</pubDate></item>
</channel></rss>"""
AVIVA = """<p><strong>August 14, 2026 - <a href="/en/press-releases/2026/half-year-results-2026/" title="x">Media statement - Aviva Canada posts half-year 2026 results</a></strong></p>
<p><strong>June 18, 2026 - <a target="_blank" href="/en/press-releases/2026/fness/" rel="noopener">Aviva Canada and FNESS team up</a></strong></p>"""
TD = """<section class='m-preview'><div class="m-preview__inner"><div class="m-preview__content"><div class="m-preview__title">
<a href="https://stories.td.com/ca/en/news/2026-10-06-burst-pipes">One in four Canadians: TD Insurance survey</a></div>
<div class="m-preview__description">Nearly half of Canadians &#039;leave&#039; homes</div>
<div class="m-preview__info"><span class="m-preview__date"> Oct 6, 2026 </span></div></div></div></section>
<section class='m-preview'><div class="m-preview__inner"><div class="m-preview__content"><div class="m-preview__title">
<a href="https://stories.td.com/ca/en/news/2026-09-30-td-bank-buyback">TD Bank Group announces share buyback</a></div>
<div class="m-preview__info"><span class="m-preview__date"> Sep 30, 2026 </span></div></div></div></section>"""


def source(kind="rss", company="IFC", hosts=("news.example.com",), terms=()):
    return NewsSource(company, f"{company.lower()}_src", kind, f"https://{hosts[0]}/feed", hosts, terms)


def test_the_approved_config_names_each_pnc_issuer_once_on_https_hosts():
    sources = load_news_sources(ROOT / "config/pnc/news_sources.yaml")
    assert sorted(item.company_id for item in sources) == ["AV", "DFY", "IFC", "TD"]
    assert all(host_allowed(item.url, item.allowed_hosts) for item in sources)
    assert next(item for item in sources if item.company_id == "TD").include_terms


def test_config_validation_rejects_duplicates_unknown_kinds_and_foreign_hosts(tmp_path):
    def write(body):
        path = tmp_path / "s.yaml"
        path.write_text("news_sources:\n" + body, encoding="utf-8")
        return path
    ok = "  - {company_id: IFC, source_id: a, kind: rss, url: 'https://x.example.com/f', allowed_hosts: [x.example.com]}\n"
    assert len(load_news_sources(write(ok))) == 1
    with pytest.raises(ValueError, match="once"):
        load_news_sources(write(ok + ok))
    with pytest.raises(ValueError, match="kind"):
        load_news_sources(write(ok.replace("rss", "scrape")))
    with pytest.raises(ValueError, match="allowed host"):
        load_news_sources(write(ok.replace("[x.example.com]", "[other.example.com]")))
    with pytest.raises(ValueError, match="allowed host"):
        load_news_sources(write(ok.replace("https://", "http://")))


def test_parsers_read_each_source_format():
    items = parse_rss(RSS)
    assert [item["title"] for item in items][:2] == ["Q3 catastrophe loss estimate", "Board appointment"]
    assert items[0]["summary"] == "Estimate & impact" and items[0]["published"] == datetime(2026, 10, 6, 21, 1, tzinfo=UTC)
    aviva = parse_aviva_list(AVIVA, "https://www.aviva.ca/en/press-releases/")
    assert aviva[0]["url"] == "https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/"
    assert aviva[1]["published"] == datetime(2026, 6, 18, tzinfo=UTC) and "FNESS" in aviva[1]["title"]
    td = parse_td_list(TD)
    assert td[0]["title"].endswith("TD Insurance survey") and td[0]["published"] == datetime(2026, 10, 6, tzinfo=UTC)
    assert td[0]["summary"] == "Nearly half of Canadians 'leave' homes"
    assert parse_date("Sep 30, 2026") == datetime(2026, 9, 30, tzinfo=UTC) and parse_date("garbage") is None and parse_date(None) is None


def test_a_feed_with_entities_is_refused():
    with pytest.raises(ValueError, match="entities"):
        parse_rss('<!DOCTYPE x [<!ENTITY a "b">]><rss><channel><item><title>t</title><link>l</link></item></channel></rss>')


def test_collection_filters_hosts_and_terms_sorts_newest_first_and_limits():
    result = collect_pnc_news([source()], fetch=lambda url, hosts: RSS, limit=1, now=NOW)
    assert [row["title"] for row in result.rows] == ["Q3 catastrophe loss estimate"]
    assert result.per_source["IFC"] == {"source_id": "ifc_src", "status": "ok", "articles": 1, "dropped_hosts": 1}
    row = result.rows[0]
    assert row["relevant_company_ids"] == ["IFC"] and row["categories"] == ["Résultats et capital"]
    assert row["fetched_at"] == NOW and len(row["article_id"]) == 32 and row["enrichment_status"] == "succeeded"
    again = collect_pnc_news([source()], fetch=lambda url, hosts: RSS, limit=1, now=NOW).rows[0]
    assert again["article_id"] == row["article_id"] and again["content_hash"] == row["content_hash"]  # idempotent keys
    td = collect_pnc_news([source("td_list", "TD", ("stories.td.com",), ("td insurance",))], fetch=lambda url, hosts: TD, now=NOW)
    assert [row["source_url"].rsplit("/", 1)[-1] for row in td.rows] == ["2026-10-06-burst-pipes"]


def test_one_failing_source_is_recorded_without_hiding_the_others():
    def fetch(url, hosts):
        if "feed" in url and "bad.example.com" in url:
            raise TimeoutError("timed out")
        return RSS
    sources = [source(company="IFC"), source(company="DFY", hosts=("bad.example.com",))]
    result = collect_pnc_news(sources, fetch=fetch, now=NOW)
    assert result.per_source["IFC"]["status"] == "ok" and result.rows
    assert result.per_source["DFY"]["status"] == "failed" and "TimeoutError" in result.per_source["DFY"]["error"]


def test_http_get_refuses_redirects_outside_the_approved_hosts(monkeypatch):
    class Response:
        def __init__(self, url, body): self.url, self.body = url, body
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return self.url
        def read(self, size): return self.body[:size]

    monkeypatch.setattr(pnc_news.urllib.request, "urlopen", lambda request, timeout: Response("https://elsewhere.example.org/x", b"ok"))
    with pytest.raises(ValueError, match="outside"):
        http_get("https://news.example.com/feed", ["news.example.com"])
    monkeypatch.setattr(pnc_news.urllib.request, "urlopen", lambda request, timeout: Response("https://news.example.com/feed", b"fine"))
    assert http_get("https://news.example.com/feed", ["news.example.com"]) == "fine"
    monkeypatch.setattr(pnc_news.urllib.request, "urlopen", lambda request, timeout: Response("https://news.example.com/feed", b"x" * (pnc_news.MAX_BYTES + 5)))
    with pytest.raises(ValueError, match="too large"):
        http_get("https://news.example.com/feed", ["news.example.com"])
