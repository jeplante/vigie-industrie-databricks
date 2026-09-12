"""Deterministic, source-faithful RSS and Atom news ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


BRONZE_COLUMNS = [
    "article_id", "source", "source_type", "company_id", "source_article_id", "source_url", "title_raw",
    "description_raw", "published_at_raw", "published_at_iso", "fetched_at", "raw_payload", "content_hash",
]
BRONZE_SCHEMA = ",".join(f"{column} string" for column in BRONZE_COLUMNS)
ALLOWED_LIVE_HOSTS = {"www150.statcan.gc.ca", "www.manulife.com", "www.sunlife.com", "www.greatwestlifeco.com", "ia.ca", "www.advisor.ca", "www.investmentexecutive.com", "www.insurancejournal.com"}
ALLOWED_CONTENT_TYPES = {"application/atom+xml", "application/rss+xml", "application/xml", "text/xml"}


@dataclass(frozen=True)
class NewsSource:
    source_id: str
    url: str
    enabled: bool = True
    source_type: str = "external_context"
    company_id: str | None = None


@dataclass(frozen=True)
class NewsBronzeLoadResult:
    bronze_object: str
    source_mode: str
    input_rows: int
    inserted_rows: int
    updated_rows: int
    final_row_count: int
    sources_succeeded: int = 1
    sources_failed: int = 0


def normalize_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    query = urlencode([
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", query, ""))


def article_id(source: str, source_article_id: str | None, source_url: str) -> str:
    material = source_article_id.strip() if source_article_id and source_article_id.strip() else normalize_url(source_url)
    return hashlib.sha256(f"{source}||{material}".encode()).hexdigest()


def content_hash(title: str, description: str, source_url: str) -> str:
    material = "||".join((" ".join(title.split()), " ".join(description.split()), normalize_url(source_url)))
    return hashlib.sha256(material.encode()).hexdigest()


def _element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _published_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _row(
    source: str,
    guid: str | None,
    url: str,
    title: str,
    description: str,
    published: str | None,
    fetched: str,
    identity_material: str | None = None,
) -> dict:
    result = {
        "article_id": hashlib.sha256(f"{source}||{identity_material}".encode()).hexdigest()
        if identity_material
        else article_id(source, guid, url),
        "source": source,
        "source_article_id": guid,
        "source_url": url,
        "title_raw": title,
        "description_raw": description,
        "published_at_raw": published,
        "published_at_iso": _published_iso(published),
        "fetched_at": fetched,
        "raw_payload": json.dumps(
            {"guid": guid, "link": url, "title": title, "description": description, "published": published},
            sort_keys=True,
        ),
    }
    result["content_hash"] = content_hash(title, description, url)
    return result


def parse_feed(payload: bytes, source: str, fetched_at: datetime | None = None) -> list[dict]:
    fetched = (fetched_at or datetime.now(UTC)).isoformat()
    root = ET.fromstring(payload)
    rows: list[dict] = []

    if root.tag.rsplit("}", 1)[-1].lower() == "feed":
        namespace = root.tag.split("}", 1)[0].lstrip("{") if "}" in root.tag else ""
        prefix = f"{{{namespace}}}" if namespace else ""
        for entry in root.findall(f"{prefix}entry"):
            guid = _element_text(entry.find(f"{prefix}id")) or None
            link = ""
            for candidate in entry.findall(f"{prefix}link"):
                rel = candidate.attrib.get("rel", "alternate")
                href = candidate.attrib.get("href", "").strip()
                if href and rel in {"alternate", ""}:
                    link = href
                    break
            title = _element_text(entry.find(f"{prefix}title"))
            description = _element_text(entry.find(f"{prefix}summary")) or _element_text(entry.find(f"{prefix}content"))
            published = _element_text(entry.find(f"{prefix}published")) or _element_text(entry.find(f"{prefix}updated")) or None
            if link and title:
                natural_id = guid.strip() if guid else normalize_url(link)
                identity_material = f"{natural_id}||{' '.join(title.split())}"
                rows.append(_row(source, guid, link, title, description, published, fetched, identity_material))
        return rows

    for item in root.findall(".//item"):
        guid = _element_text(item.find("guid")) or None
        url = _element_text(item.find("link"))
        title = _element_text(item.find("title"))
        description = _element_text(item.find("description"))
        published = _element_text(item.find("pubDate")) or None
        if url and title:
            rows.append(_row(source, guid, url, title, description, published, fetched))
    return rows


def parse_rss(payload: bytes, source: str, fetched_at: datetime | None = None) -> list[dict]:
    """Backward-compatible entry point retained for Slice 6 callers."""
    return parse_feed(payload, source, fetched_at)


def parse_sources_json(value: str) -> list[NewsSource]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("sources_json must be valid JSON") from exc
    if not isinstance(raw, list) or not raw:
        raise ValueError("sources_json must be a non-empty list")
    sources: list[NewsSource] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"source_id", "url", "enabled", "source_type", "company_id"}:
            raise ValueError("Each source must contain only source_id, url, enabled, source_type, and company_id")
        source_id = str(item.get("source_id", "")).strip()
        url = str(item.get("url", "")).strip()
        enabled = item.get("enabled", True)
        source_type = item.get("source_type", "external_context")
        company_id = item.get("company_id")
        if not source_id or not source_id.replace("_", "").isalnum():
            raise ValueError("source_id must contain only letters, numbers, and underscores")
        if source_id in seen:
            raise ValueError(f"Duplicate source_id: {source_id}")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        if source_type not in {"external_context", "official_insurer", "editorial_insurance", "editorial_wealth"}:
            raise ValueError("source_type is unsupported")
        if source_type == "official_insurer" and company_id not in {"MFC", "SLF", "GWO", "IAG"}:
            raise ValueError("official_insurer sources require a configured company_id")
        validate_live_url(url)
        seen.add(source_id)
        sources.append(NewsSource(source_id, url, enabled, source_type, company_id))
    if not any(source.enabled for source in sources):
        raise ValueError("At least one source must be enabled")
    return sources


def validate_live_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_LIVE_HOSTS:
        raise ValueError("Live source URL must use HTTPS and an approved host")
    if parts.username or parts.password or parts.port not in {None, 443}:
        raise ValueError("Live source URL must not include credentials or a non-standard port")


def acquire_feed(
    source_url: str,
    source: str,
    max_articles: int = 25,
    timeout_seconds: int = 20,
    max_response_bytes: int = 1_000_000,
) -> list[dict]:
    validate_live_url(source_url)
    if not 1 <= max_articles <= 100:
        raise ValueError("max_articles must be between 1 and 100")
    request = Request(source_url, headers={"User-Agent": "VigieDatabricks/1.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get_content_type().lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Unsupported feed content type: {content_type}")
        payload = response.read(max_response_bytes + 1)
    if len(payload) > max_response_bytes:
        raise ValueError("Feed response exceeds the configured size limit")
    return parse_feed(payload, source)[:max_articles]


def acquire_rss(source_url: str, source: str, max_articles: int = 5) -> list[dict]:
    """Backward-compatible wrapper retained for Slice 6 callers."""
    return acquire_feed(source_url, source, max_articles)


def acquire_sources(sources: Iterable[NewsSource], max_articles: int = 25) -> tuple[list[dict], int, int]:
    rows: list[dict] = []
    succeeded = 0
    failed = 0
    for source in sources:
        if not source.enabled:
            continue
        try:
            acquired = acquire_feed(source.url, source.source_id, max_articles=max_articles)
            for row in acquired:
                row["source_type"] = source.source_type
                row["company_id"] = source.company_id
            rows.extend(acquired)
            succeeded += 1
        except Exception:
            failed += 1
    if succeeded == 0:
        raise ValueError("All enabled news sources failed")
    return rows, succeeded, failed


def _deduplicate_rows(rows: Iterable[dict]) -> list[dict]:
    """Keep one deterministic source row per article_id before Delta MERGE."""
    selected: dict[str, dict] = {}
    for row in rows:
        key = row["article_id"]
        current = selected.get(key)
        rank = (row.get("published_at_iso") or "", row["content_hash"])
        current_rank = (
            (current.get("published_at_iso") or "", current["content_hash"])
            if current
            else None
        )
        if current_rank is None or rank > current_rank:
            selected[key] = row
    return [selected[key] for key in sorted(selected)]


def _merge(spark: SparkSession, source_df: DataFrame, target: str) -> tuple[int, int]:
    if not spark.catalog.tableExists(target):
        source_df.write.format("delta").mode("overwrite").saveAsTable(target)
        return source_df.count(), 0
    existing = spark.table(target).select("article_id", "content_hash").alias("t")
    incoming = source_df.alias("s")
    inserted = incoming.join(existing, "article_id", "left_anti").count()
    updated = existing.join(incoming, "article_id").where(F.col("t.content_hash") != F.col("s.content_hash")).count()
    view = "vigie_news_bronze_source"
    source_df.createOrReplaceTempView(view)
    try:
        assignments = ", ".join(f"{column}=s.{column}" for column in BRONZE_COLUMNS)
        columns = ", ".join(BRONZE_COLUMNS)
        values = ", ".join(f"s.{column}" for column in BRONZE_COLUMNS)
        spark.sql(f"MERGE INTO {target} t USING {view} s ON t.article_id=s.article_id WHEN MATCHED AND NOT (t.content_hash <=> s.content_hash) THEN UPDATE SET {assignments} WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values})")
    finally:
        spark.catalog.dropTempView(view)
    return inserted, updated


def load_bronze_news(
    spark: SparkSession,
    source_mode: str,
    source_url: str,
    fixture_path: str | None,
    bronze_object: str,
    source: str = "rss_fixture",
    max_articles: int = 5,
    sources_json: str | None = None,
) -> NewsBronzeLoadResult:
    sources_succeeded = 1
    sources_failed = 0
    if source_mode == "fixture":
        if not fixture_path:
            raise ValueError("fixture_path is required in fixture mode")
        payload = Path(fixture_path).read_bytes()
        rows = parse_feed(payload, source) if payload.lstrip().startswith(b"<") else json.loads(payload.decode("utf-8"))
    elif source_mode == "live":
        if sources_json:
            rows, sources_succeeded, sources_failed = acquire_sources(parse_sources_json(sources_json), max_articles)
        else:
            rows = acquire_feed(source_url, source, max_articles)
    else:
        raise ValueError(f"Unsupported news source mode: {source_mode}")
    if not rows:
        raise ValueError("News source produced no valid articles")
    rows = _deduplicate_rows(rows)
    for row in rows:
        row.setdefault("published_at_iso", row.get("published_at_raw"))
        row.setdefault("source_type", "external_context")
        row.setdefault("company_id", None)
    # Spark Connect cannot infer the type of an all-null company_id column.
    # The explicit schema also keeps fixture and live ingestion identical.
    source_df = spark.createDataFrame(rows, schema=BRONZE_SCHEMA).select(*BRONZE_COLUMNS)
    inserted, updated = _merge(spark, source_df, bronze_object)
    return NewsBronzeLoadResult(
        bronze_object, source_mode, len(rows), inserted, updated, spark.table(bronze_object).count(),
        sources_succeeded, sources_failed,
    )
