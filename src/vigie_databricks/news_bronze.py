"""Deterministic, source-faithful RSS news ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


BRONZE_COLUMNS = [
    "article_id", "source", "source_article_id", "source_url", "title_raw",
    "description_raw", "published_at_raw", "published_at_iso", "fetched_at", "raw_payload", "content_hash",
]


@dataclass(frozen=True)
class NewsBronzeLoadResult:
    bronze_object: str
    source_mode: str
    input_rows: int
    inserted_rows: int
    updated_rows: int
    final_row_count: int


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


def _text(element: ET.Element | None) -> str:
    return " ".join((element.text or "").split()) if element is not None else ""


def parse_rss(payload: bytes, source: str, fetched_at: datetime | None = None) -> list[dict]:
    fetched = (fetched_at or datetime.now(UTC)).isoformat()
    root = ET.fromstring(payload)
    rows = []
    for item in root.findall(".//item"):
        guid = _text(item.find("guid")) or None
        url = _text(item.find("link"))
        title = _text(item.find("title"))
        description = _text(item.find("description"))
        published = _text(item.find("pubDate")) or None
        if not url or not title:
            continue
        row = {
            "article_id": article_id(source, guid, url),
            "source": source,
            "source_article_id": guid,
            "source_url": url,
            "title_raw": title,
            "description_raw": description,
            "published_at_raw": published,
            "published_at_iso": parsedate_to_datetime(published).astimezone(UTC).isoformat() if published else None,
            "fetched_at": fetched,
            "raw_payload": json.dumps({"guid": guid, "link": url, "title": title, "description": description, "pubDate": published}, sort_keys=True),
        }
        row["content_hash"] = content_hash(title, description, url)
        rows.append(row)
    return rows


def acquire_rss(source_url: str, source: str, max_articles: int = 5) -> list[dict]:
    request = Request(source_url, headers={"User-Agent": "VigieDatabricks/1.0"})
    with urlopen(request, timeout=20) as response:
        return parse_rss(response.read(1_000_000), source)[:max_articles]


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


def load_bronze_news(spark: SparkSession, source_mode: str, source_url: str, fixture_path: str | None, bronze_object: str, source: str = "rss_fixture", max_articles: int = 5) -> NewsBronzeLoadResult:
    if source_mode == "fixture":
        if not fixture_path:
            raise ValueError("fixture_path is required in fixture mode")
        payload = Path(fixture_path).read_bytes()
        if payload.lstrip().startswith(b"<"):
            rows = parse_rss(payload, source)
        else:
            rows = json.loads(payload.decode("utf-8"))
    elif source_mode == "live":
        rows = acquire_rss(source_url, source, max_articles)
    else:
        raise ValueError(f"Unsupported news source mode: {source_mode}")
    if not rows:
        raise ValueError("RSS source produced no valid articles")
    for row in rows:
        row.setdefault("published_at_iso", row.get("published_at_raw"))
    source_df = spark.createDataFrame(rows).select(*BRONZE_COLUMNS)
    inserted, updated = _merge(spark, source_df, bronze_object)
    return NewsBronzeLoadResult(bronze_object, source_mode, len(rows), inserted, updated, spark.table(bronze_object).count())