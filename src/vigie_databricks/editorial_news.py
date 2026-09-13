"""Bounded, deterministic ingestion of approved insurance and wealth media."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from pyspark.sql import SparkSession

from vigie_databricks.news_bronze import NewsSource, acquire_sources, parse_sources_json


EDITORIAL_SCHEMA = "article_id string,source string,source_type string,source_url string,title string,summary string,published_at timestamp,relevant_company_ids array<string>,categories array<string>,enrichment_status string,fetched_at timestamp,content_hash string"
COMPANY_TERMS = {
    "MFC": ("manulife", "john hancock"), "SLF": ("sun life",),
    "GWO": ("great-west lifeco", "great west lifeco", "canada life"),
    "IAG": ("ia financial", "i a financial", "industrial alliance"),
}


def load_sources(path: str | Path) -> list[NewsSource]:
    return parse_sources_json(Path(path).read_text(encoding="utf-8"))


def _published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def editorial_row(row: dict[str, Any], source: NewsSource) -> dict[str, Any]:
    text = f"{row.get('title_raw', '')} {row.get('description_raw', '')}".lower()
    companies = [company for company, terms in COMPANY_TERMS.items() if any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)]
    category = "Gestion de patrimoine" if source.source_type == "editorial_wealth" else "Médias assurance"
    return {
        "article_id": row["article_id"], "source": source.source_id, "source_type": source.source_type,
        "source_url": row["source_url"], "title": row["title_raw"], "summary": row.get("description_raw") or "",
        "published_at": _published(row.get("published_at_iso")), "relevant_company_ids": companies,
        "categories": [category], "enrichment_status": "succeeded", "fetched_at": _published(row.get("fetched_at")) or datetime.now(UTC),
        "content_hash": row["content_hash"],
    }


def load_editorial_news(spark: SparkSession, sources_path: str, target: str, *, dry_run: bool = True, max_articles: int = 15) -> dict[str, Any]:
    sources = load_sources(sources_path)
    rows, succeeded, failed = acquire_sources(sources, max_articles=max_articles)
    source_by_id = {source.source_id: source for source in sources}
    output = [editorial_row(row, source_by_id[row["source"]]) for row in rows]
    result = {"sources_succeeded": succeeded, "sources_failed": failed, "articles": len(output), "inserted_rows": 0, "updated_rows": 0, "dry_run": dry_run}
    if dry_run:
        return result
    source = spark.createDataFrame(output, EDITORIAL_SCHEMA)
    if not spark.catalog.tableExists(target):
        source.write.format("delta").mode("overwrite").saveAsTable(target)
        result["inserted_rows"] = len(output)
        return result
    existing = spark.table(target).select("article_id", "content_hash").alias("t")
    result["inserted_rows"] = source.alias("s").join(existing, "article_id", "left_anti").count()
    result["updated_rows"] = source.alias("s").join(existing, "article_id").where("NOT (s.content_hash <=> t.content_hash)").count()
    view = f"vigie_editorial_news_{uuid4().hex}"
    source.createOrReplaceTempView(view)
    try:
        spark.sql(f"MERGE INTO {target} t USING {view} s ON t.article_id=s.article_id WHEN MATCHED AND NOT (t.content_hash <=> s.content_hash) THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
    finally:
        spark.catalog.dropTempView(view)
    return result
