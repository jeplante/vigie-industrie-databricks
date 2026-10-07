"""Bounded, allowlisted collection of official P&C issuer news.

News is context only: it never feeds or alters a KPI. Each source is read independently, every
article URL must be https on an approved host, and one failing source never hides the others.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import hashlib
import html
from pathlib import Path
import re
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse
import urllib.request

import yaml

SCHEMA = ("article_id string,source string,source_url string,title string,summary string,published_at timestamp,"
          "company_id string,relevant_company_ids array<string>,categories array<string>,enrichment_status string,"
          "fetched_at timestamp,content_hash string")
PNC_COMPANIES = ("IFC", "AV", "TD", "DFY")
KINDS = ("rss", "aviva_list", "td_list")
FINANCIAL = re.compile(r"results|earnings|dividend|catastrophe|debenture|subordinated|acquisition|guidance|\bcapital\b", re.I)
MAX_BYTES = 2_000_000
USER_AGENT = "vigie-databricks/0.10 (official newsroom reader; contact jerome.plante@hotmail.com)"
MONTHS = {name: number for number, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"), 1)}


@dataclass(frozen=True)
class NewsSource:
    company_id: str
    source_id: str
    kind: str
    url: str
    allowed_hosts: tuple[str, ...]
    include_terms: tuple[str, ...] = ()


@dataclass
class NewsResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    per_source: dict[str, dict[str, Any]] = field(default_factory=dict)


def host_allowed(url: str, hosts: Iterable[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "") in set(hosts)


def load_news_sources(path: str | Path) -> list[NewsSource]:
    entries = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["news_sources"]
    sources, seen = [], set()
    for entry in entries:
        source = NewsSource(entry["company_id"], entry["source_id"], entry["kind"], entry["url"],
                            tuple(entry["allowed_hosts"]), tuple(term.lower() for term in entry.get("include_terms", ())))
        if source.company_id not in PNC_COMPANIES or source.company_id in seen:
            raise ValueError(f"news source must name each P&C issuer once: {source.company_id}")
        if source.kind not in KINDS:
            raise ValueError(f"unsupported news source kind: {source.kind}")
        if not host_allowed(source.url, source.allowed_hosts):
            raise ValueError(f"news source URL is not https on an allowed host: {source.url}")
        seen.add(source.company_id)
        sources.append(source)
    return sources


def http_get(url: str, hosts: Iterable[str], timeout: float = 20) -> str:
    """Read one page, refusing redirects that leave the approved hosts and oversized bodies."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if not host_allowed(response.geturl(), hosts):
            raise ValueError("redirected outside the approved hosts")
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("response too large")
    return body.decode("utf-8", "replace")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def parse_date(value: str | None) -> datetime | None:
    """RFC 2822 (RSS), 'August 14, 2026' (Aviva), 'Oct 6, 2026' (TD) or an ISO date."""
    if not value:
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        pass
    match = re.fullmatch(r"([A-Za-z]+)\.? (\d{1,2}), (\d{4})", value)
    if match:
        month = MONTHS.get(next((name for name in MONTHS if name.startswith(match.group(1).lower()[:3])), ""))
        if month:
            return datetime(int(match.group(3)), month, int(match.group(2)), tzinfo=UTC)
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=UTC) if match else None


def parse_rss(xml_text: str) -> list[dict[str, Any]]:
    if re.search(r"<!DOCTYPE|<!ENTITY", xml_text, re.I):
        raise ValueError("feed declares a DTD or entities")
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml_text, re.S):
        def field_of(tag: str) -> str:
            found = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return _text(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", found.group(1), flags=re.S)) if found else ""
        title, link = field_of("title"), field_of("link")
        if title and link:
            items.append({"title": title, "url": link, "summary": field_of("description"), "published": parse_date(field_of("pubDate"))})
    return items


def parse_aviva_list(page: str, base_url: str) -> list[dict[str, Any]]:
    """`<strong>August 14, 2026 - <a href="/en/press-releases/2026/slug/">Title</a></strong>`."""
    items = []
    pattern = re.compile(r"<strong>\s*([A-Za-z]+ \d{1,2}, \d{4})\s*-\s*<a[^>]*href=\"([^\"]*/press-releases/[^\"]+)\"[^>]*>(.*?)</a>", re.S)
    for date, href, title in pattern.findall(page):
        if _text(title):
            items.append({"title": _text(title), "url": urljoin(base_url, href), "summary": "", "published": parse_date(date)})
    return items


def parse_td_list(page: str) -> list[dict[str, Any]]:
    """TD `m-preview` cards: title link (URL carries the date), description and printed date."""
    items = []
    for card in re.findall(r"<div class=\"m-preview__content\">(.*?)</section>", page, re.S):
        link = re.search(r"<div class=\"m-preview__title\">\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", card, re.S)
        if not link:
            continue
        description = re.search(r"<div class=\"m-preview__description\">(.*?)</div>", card, re.S)
        printed = re.search(r"<span class=\"m-preview__date\">(.*?)</span>", card, re.S)
        from_url = re.search(r"/news/(\d{4}-\d{2}-\d{2})-", link.group(1))
        items.append({"title": _text(link.group(2)), "url": link.group(1), "summary": _text(description.group(1)) if description else "",
                      "published": parse_date(_text(printed.group(1)) if printed else None) or parse_date(from_url.group(1) if from_url else None)})
    return items


def parse_source(source: NewsSource, page: str) -> list[dict[str, Any]]:
    if source.kind == "rss":
        return parse_rss(page)
    if source.kind == "aviva_list":
        return parse_aviva_list(page, source.url)
    return parse_td_list(page)


def build_row(source: NewsSource, item: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
    title, summary, published = item["title"], item["summary"][:500], item["published"]
    digest = hashlib.sha256("|".join((title, summary, published.isoformat() if published else "")).encode("utf-8")).hexdigest()
    return {
        "article_id": hashlib.sha256(item["url"].encode("utf-8")).hexdigest()[:32], "source": source.source_id,
        "source_url": item["url"], "title": title, "summary": summary, "published_at": published,
        "company_id": source.company_id, "relevant_company_ids": [source.company_id],
        "categories": ["Résultats et capital" if FINANCIAL.search(title) else "Communiqué"],
        "enrichment_status": "succeeded", "fetched_at": fetched_at, "content_hash": digest,
    }


def collect_pnc_news(
    sources: Iterable[NewsSource],
    *,
    limit: int = 10,
    fetch: Callable[[str, Iterable[str]], str] = http_get,
    now: datetime | None = None,
) -> NewsResult:
    """Read every source independently; a failure is recorded per source and never raised."""
    now = now or datetime.now(UTC)
    result = NewsResult()
    for source in sources:
        try:
            items = parse_source(source, fetch(source.url, source.allowed_hosts))
            kept = [item for item in items if host_allowed(item["url"], source.allowed_hosts)]
            if source.include_terms:
                kept = [item for item in kept if any(term in f"{item['title']} {item['summary']}".lower() for term in source.include_terms)]
            kept.sort(key=lambda item: item["published"] or datetime.min.replace(tzinfo=UTC), reverse=True)
            result.rows.extend(build_row(source, item, now) for item in kept[:limit])
            result.per_source[source.company_id] = {"source_id": source.source_id, "status": "ok", "articles": len(kept[:limit]),
                                                    "dropped_hosts": len(items) - len([i for i in items if host_allowed(i["url"], source.allowed_hosts)])}
        except Exception as error:  # one source down must not hide the others
            result.per_source[source.company_id] = {"source_id": source.source_id, "status": "failed", "articles": 0,
                                                    "error": f"{type(error).__name__}: {str(error)[:160]}"}
    return result
