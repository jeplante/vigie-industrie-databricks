"""Databricks task: collect official P&C newsroom items into P&C-only tables (context, never KPIs)."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from vigie_databricks.pnc_news import SCHEMA, collect_pnc_news, load_news_sources

AUDIT_SCHEMA = ("run_id string,observed_at timestamp,sources_succeeded int,sources_failed int,articles int,"
                "inserted_rows int,updated_rows int,per_source_json string")


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
    failed = {company: info for company, info in result.per_source.items() if info["status"] != "ok"}
    summary = {"sources_succeeded": len(result.per_source) - len(failed), "sources_failed": len(failed),
               "articles": len(result.rows), "per_source": result.per_source, "dry_run": args.dry_run == "true"}
    if args.dry_run == "true":
        print(json.dumps(summary, default=str, sort_keys=True), flush=True)
        if failed:
            raise ValueError(f"P&C news sources failed: {', '.join(sorted(failed))}")
        return

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    target, audit_table = f"{args.namespace}.pnc_official_news", f"{args.namespace}.pnc_news_audit"
    if not spark.catalog.tableExists(target):
        spark.createDataFrame([], SCHEMA).write.format("delta").saveAsTable(target)
    inserted = updated = 0
    if result.rows:
        source = spark.createDataFrame(result.rows, SCHEMA)
        old = spark.table(target).select("article_id", "content_hash")
        inserted = source.join(old, "article_id", "left_anti").count()
        updated = source.alias("s").join(old.alias("t"), "article_id").where("s.content_hash <> t.content_hash").count()
        view = "pnc_official_news_" + uuid4().hex
        source.createOrReplaceTempView(view)
        try:
            spark.sql(f"MERGE INTO {target} t USING {view} s ON t.article_id=s.article_id "
                      "WHEN MATCHED AND t.content_hash <> s.content_hash THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
        finally:
            spark.catalog.dropTempView(view)
    audit = {"run_id": args.run_id or uuid4().hex, "observed_at": datetime.now(UTC), "sources_succeeded": summary["sources_succeeded"],
             "sources_failed": summary["sources_failed"], "articles": len(result.rows), "inserted_rows": inserted,
             "updated_rows": updated, "per_source_json": json.dumps(result.per_source, sort_keys=True)}
    spark.createDataFrame([audit], AUDIT_SCHEMA).write.format("delta").mode("append").saveAsTable(audit_table)
    print(json.dumps({**summary, "inserted_rows": inserted, "updated_rows": updated}, default=str, sort_keys=True), flush=True)
    if failed:  # successes are kept; the failure is surfaced so the Job alerts
        raise ValueError(f"P&C news sources failed: {', '.join(sorted(failed))}")


if __name__ == "__main__":
    main()
