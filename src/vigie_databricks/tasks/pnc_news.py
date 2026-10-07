"""Databricks task: collect official P&C newsroom items and sector media into P&C-only tables (context, never KPIs).

Publication rule, the same for both universes: the sources that answered are published, a failing source keeps
its last-known articles (MERGE never deletes), the audit names it, and the run fails so the Job alerts.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from vigie_databricks.pnc_news import (EDITORIAL_SCHEMA, SCHEMA, collect_pnc_editorial, collect_pnc_news, load_editorial_sources,
                                      load_news_sources)

AUDIT_SCHEMA = ("run_id string,observed_at timestamp,sources_succeeded int,sources_failed int,articles int,"
                "inserted_rows int,updated_rows int,per_source_json string,editorial_articles int,editorial_json string")
# As for the life sector media task: below this many answering feeds the sector-media collection is a failure.
MINIMUM_EDITORIAL_SOURCES = 2


def merge_articles(spark, rows, schema, target):
    """Idempotent upsert keyed by article_id; returns (inserted, updated). Never deletes."""
    if not spark.catalog.tableExists(target):
        spark.createDataFrame([], schema).write.format("delta").saveAsTable(target)
    if not rows:
        return 0, 0
    source = spark.createDataFrame(rows, schema)
    old = spark.table(target).select("article_id", "content_hash")
    inserted = source.join(old, "article_id", "left_anti").count()
    updated = source.alias("s").join(old.alias("t"), "article_id").where("s.content_hash <> t.content_hash").count()
    view = "pnc_news_" + uuid4().hex
    source.createOrReplaceTempView(view)
    try:
        spark.sql(f"MERGE INTO {target} t USING {view} s ON t.article_id=s.article_id "
                  "WHEN MATCHED AND t.content_hash <> s.content_hash THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
    finally:
        spark.catalog.dropTempView(view)
    return inserted, updated


def failures(official, editorial):
    """Why the run must alert, or an empty list."""
    problems = []
    failed = sorted(company for company, info in official.per_source.items() if info["status"] != "ok")
    if failed:
        problems.append(f"P&C news sources failed: {', '.join(failed)}")
    answered = sum(info["status"] == "ok" for info in editorial.per_source.values())
    if editorial.per_source and answered < MINIMUM_EDITORIAL_SOURCES:
        problems.append(f"P&C sector media: {answered} feed(s) answered, minimum {MINIMUM_EDITORIAL_SOURCES}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-directory", required=True, help="directory holding news_sources.yaml")
    parser.add_argument("--namespace", default="workspace.vigie")
    parser.add_argument("--dry-run", choices=("true", "false"), default="true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    sources = load_news_sources(Path(args.config_directory) / "news_sources.yaml")
    result = collect_pnc_news(sources, limit=args.limit)
    editorial = collect_pnc_editorial(load_editorial_sources(Path(args.config_directory) / "news_sources.yaml"))
    failed = {company: info for company, info in result.per_source.items() if info["status"] != "ok"}
    problems = failures(result, editorial)
    summary = {"sources_succeeded": len(result.per_source) - len(failed), "sources_failed": len(failed),
               "articles": len(result.rows), "per_source": result.per_source, "editorial_articles": len(editorial.rows),
               "editorial": editorial.per_source, "dry_run": args.dry_run == "true"}
    if args.dry_run == "true":
        print(json.dumps(summary, default=str, sort_keys=True), flush=True)
        if problems:
            raise ValueError("; ".join(problems))
        return

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    target, audit_table = f"{args.namespace}.pnc_official_news", f"{args.namespace}.pnc_news_audit"
    inserted, updated = merge_articles(spark, result.rows, SCHEMA, target)
    editorial_inserted, _ = merge_articles(spark, editorial.rows, EDITORIAL_SCHEMA, f"{args.namespace}.pnc_editorial_news")
    audit = {"run_id": args.run_id or uuid4().hex, "observed_at": datetime.now(UTC), "sources_succeeded": summary["sources_succeeded"],
             "sources_failed": summary["sources_failed"], "articles": len(result.rows), "inserted_rows": inserted,
             "updated_rows": updated, "per_source_json": json.dumps(result.per_source, sort_keys=True),
             "editorial_articles": len(editorial.rows), "editorial_json": json.dumps(editorial.per_source, sort_keys=True)}
    # mergeSchema adds the two sector-media columns to the existing audit table on first use.
    spark.createDataFrame([audit], AUDIT_SCHEMA).write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(audit_table)
    print(json.dumps({**summary, "inserted_rows": inserted, "updated_rows": updated, "editorial_inserted_rows": editorial_inserted},
                     default=str, sort_keys=True), flush=True)
    if problems:  # successes are kept; the failure is surfaced so the Job alerts
        raise ValueError("; ".join(problems))


if __name__ == "__main__":
    main()
