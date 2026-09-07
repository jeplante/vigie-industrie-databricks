"""Delta persistence helpers for insurer Finance documents and run audits."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pyspark.sql import SparkSession

from vigie_databricks.finance_documents import (
    FINANCE_RUN_AUDIT_SCHEMA,
    FINANCIAL_DOCUMENT_SCHEMA,
    FinancialDocument,
)


def _upsert_rows(
    spark: SparkSession,
    object_name: str,
    rows: list[dict[str, Any]],
    schema: str,
    key: str,
) -> None:
    if not spark.catalog.tableExists(object_name):
        (
            spark.createDataFrame([], schema=schema)
            .write.format("delta")
            .mode("overwrite")
            .saveAsTable(object_name)
        )
    if not rows:
        return
    source = spark.createDataFrame(rows, schema=schema)
    view = f"vigie_finance_upsert_{uuid4().hex}"
    source.createOrReplaceTempView(view)
    try:
        spark.sql(
            f"MERGE INTO {object_name} t USING {view} s ON t.{key}=s.{key} "
            "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *"
        )
    finally:
        spark.catalog.dropTempView(view)


def upsert_financial_documents(
    spark: SparkSession,
    object_name: str,
    documents: Iterable[FinancialDocument],
) -> None:
    if spark.catalog.tableExists(object_name):
        columns = {field.name for field in spark.table(object_name).schema.fields}
        additions = []
        if "raw_content_path" not in columns:
            additions.append("raw_content_path STRING")
        if "reporting_period" not in columns:
            additions.append("reporting_period STRING")
        if additions:
            spark.sql(f"ALTER TABLE {object_name} ADD COLUMNS ({', '.join(additions)})")
    _upsert_rows(
        spark,
        object_name,
        [asdict(document) for document in documents],
        FINANCIAL_DOCUMENT_SCHEMA,
        "document_id",
    )


def load_financial_document_index(spark: SparkSession, object_name: str) -> dict[str, dict[str, Any]]:
    if not spark.catalog.tableExists(object_name):
        return {}
    return {row["source_url"]: row.asDict(recursive=True) for row in spark.table(object_name).collect()}


def upsert_finance_run_audit(
    spark: SparkSession,
    object_name: str,
    audit: dict[str, Any],
) -> None:
    if spark.catalog.tableExists(object_name):
        columns = {field.name for field in spark.table(object_name).schema.fields}
        additions = []
        if "ai_model_calls" not in columns:
            additions.append("ai_model_calls LONG")
        if "retention_deleted_files" not in columns:
            additions.append("retention_deleted_files LONG")
        if additions:
            spark.sql(f"ALTER TABLE {object_name} ADD COLUMNS ({', '.join(additions)})")
    _upsert_rows(spark, object_name, [audit], FINANCE_RUN_AUDIT_SCHEMA, "run_id")


def enforce_finance_retention(
    spark: SparkSession,
    documents_object: str,
    audit_object: str,
    raw_volume: str,
    *,
    raw_days: int,
    failed_days: int,
    stale_audit_days: int,
    now: datetime | None = None,
) -> int:
    """Expire raw files and old technical failures while retaining current audits."""
    current = now or datetime.now(UTC)
    deleted = 0
    if spark.catalog.tableExists(documents_object):
        cutoff = current - timedelta(days=raw_days)
        rows = spark.table(documents_object).where("raw_content_path IS NOT NULL").collect()
        root = Path(raw_volume).resolve()
        expired_ids = []
        for row in rows:
            fetched_at = row["fetched_at"]
            path = Path(row["raw_content_path"]).resolve()
            if fetched_at and fetched_at.replace(tzinfo=UTC) < cutoff and root in path.parents:
                if path.exists():
                    path.unlink()
                    deleted += 1
                expired_ids.append(row["document_id"])
        if expired_ids:
            ids = spark.createDataFrame([(value,) for value in expired_ids], "document_id string")
            ids.createOrReplaceTempView("vigie_expired_finance_documents")
            spark.sql(f"MERGE INTO {documents_object} t USING vigie_expired_finance_documents s ON t.document_id=s.document_id WHEN MATCHED THEN UPDATE SET raw_content_path=NULL")
            spark.catalog.dropTempView("vigie_expired_finance_documents")
        failed_cutoff = current - timedelta(days=failed_days)
        spark.sql(f"DELETE FROM {documents_object} WHERE acquisition_status='failed' AND fetched_at < TIMESTAMP '{failed_cutoff.isoformat()}'")
    if spark.catalog.tableExists(audit_object):
        stale_cutoff = current - timedelta(days=stale_audit_days)
        spark.sql(f"DELETE FROM {audit_object} WHERE quality_status='stale' AND observed_at < TIMESTAMP '{stale_cutoff.isoformat()}'")
    return deleted
