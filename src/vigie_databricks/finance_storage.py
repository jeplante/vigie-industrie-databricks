"""Delta persistence helpers for insurer Finance documents and run audits."""

from __future__ import annotations

from dataclasses import asdict
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
        if "raw_content_path" not in columns:
            spark.sql(f"ALTER TABLE {object_name} ADD COLUMNS (raw_content_path STRING)")
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
    _upsert_rows(spark, object_name, [audit], FINANCE_RUN_AUDIT_SCHEMA, "run_id")
