"""Slice 2 Silver snapshot normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable
from uuid import uuid4

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F


MATERIAL_COLUMNS = ["company_id", "metric_id", "period_id", "value"]
PERIOD_PATTERN = r"^\d{4}Q[1-4]$"
REJECTION_PRECEDENCE = (
    "missing_observation_id",
    "missing_company_id",
    "missing_metric_id",
    "missing_period_id",
    "invalid_period_id",
    "invalid_value",
    "invalid_ingested_at",
)


@dataclass(frozen=True)
class SilverLoadResult:
    """Operational counters for one Silver synchronization execution."""

    silver_object: str
    bronze_input_rows: int
    bronze_structurally_valid_rows: int
    bronze_rejected_rows_total: int
    bronze_rejected_rows_by_reason: dict[str, int]
    silver_batch_rows_after_dedup: int
    inserted_rows: int
    updated_rows: int
    silver_deleted_rows: int
    silver_final_row_count: int
    bronze_distinct_valid_observation_ids: int
    reconciliation_delta: int


def classify_rejection_reason(row: dict[str, Any]) -> str | None:
    """Return the first deterministic rejection reason for a normalized Bronze row."""
    normalized_strings = {
        "observation_id": _normalized_string_value(row.get("observation_id")),
        "company_id": _normalized_string_value(row.get("company_id")),
        "metric_id": _normalized_string_value(row.get("metric_id")),
        "period_id": _normalized_string_value(row.get("period_id")),
    }

    checks = {
        "missing_observation_id": lambda: not normalized_strings["observation_id"],
        "missing_company_id": lambda: not normalized_strings["company_id"],
        "missing_metric_id": lambda: not normalized_strings["metric_id"],
        "missing_period_id": lambda: not normalized_strings["period_id"],
        "invalid_period_id": lambda: not _matches_period_pattern(normalized_strings["period_id"] or ""),
        "invalid_value": lambda: not _is_finite_python_number(row.get("value")),
        "invalid_ingested_at": lambda: row.get("ingested_at") is None,
    }

    for reason in REJECTION_PRECEDENCE:
        if checks[reason]():
            return reason
    return None


def _normalized_string_value(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _matches_period_pattern(value: str) -> bool:
    return bool(re.match(PERIOD_PATTERN, value))


def _is_finite_python_number(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _is_finite_spark_number(column: F.Column) -> F.Column:
    return column.isNotNull() & ~F.isnan(column) & (F.abs(column) != F.lit(float("inf")))


def _material_payload_hash() -> F.Column:
    parts = [F.coalesce(F.col(column).cast("string"), F.lit("<NULL>")) for column in MATERIAL_COLUMNS]
    return F.sha2(F.concat_ws("||", *parts), 256)


def _material_change_condition_sql(target_alias: str = "t", source_alias: str = "s") -> str:
    comparisons = [
        f"{target_alias}.{column} <=> {source_alias}.{column}" for column in MATERIAL_COLUMNS
    ]
    return "NOT (" + " AND ".join(comparisons) + ")"


def _required_columns_present(df: DataFrame, required: Iterable[str]) -> bool:
    available = set(df.columns)
    return all(column in available for column in required)


def _normalize_bronze_rows(bronze_df: DataFrame) -> DataFrame:
    return bronze_df.select(
        F.trim(F.col("observation_id").cast("string")).alias("observation_id"),
        F.trim(F.col("company_id").cast("string")).alias("company_id"),
        F.trim(F.col("metric_id").cast("string")).alias("metric_id"),
        F.trim(F.col("period_id").cast("string")).alias("period_id"),
        F.col("value").cast("double").alias("value"),
        F.to_timestamp("ingested_at").alias("ingested_at"),
    )


def _rejection_reason_column() -> F.Column:
    predicates = {
        "missing_observation_id": F.col("observation_id").isNull()
        | (F.length(F.col("observation_id")) == 0),
        "missing_company_id": F.col("company_id").isNull() | (F.length(F.col("company_id")) == 0),
        "missing_metric_id": F.col("metric_id").isNull() | (F.length(F.col("metric_id")) == 0),
        "missing_period_id": F.col("period_id").isNull() | (F.length(F.col("period_id")) == 0),
        "invalid_period_id": ~F.col("period_id").rlike(PERIOD_PATTERN),
        "invalid_value": ~_is_finite_spark_number(F.col("value")),
        "invalid_ingested_at": F.col("ingested_at").isNull(),
    }

    expression = None
    for reason in REJECTION_PRECEDENCE:
        if expression is None:
            expression = F.when(predicates[reason], F.lit(reason))
        else:
            expression = expression.when(predicates[reason], F.lit(reason))

    if expression is None:
        raise ValueError("REJECTION_PRECEDENCE must not be empty")
    return expression


def _merge_into_silver_table(
    spark: SparkSession,
    source_df: DataFrame,
    silver_object: str,
    material_change_condition: str,
) -> None:
    temp_view_name = f"vigie_silver_merge_source_{uuid4().hex}"
    source_df.createOrReplaceTempView(temp_view_name)
    try:
        columns = [
            "observation_id",
            "company_id",
            "metric_id",
            "period_id",
            "value",
            "ingested_at",
            "silver_record_hash",
            "silver_normalized_at",
        ]
        update_assignments = ", ".join([f"{column} = s.{column}" for column in columns])
        insert_columns = ", ".join(columns)
        insert_values = ", ".join([f"s.{column}" for column in columns])

        spark.sql(
            f"""
            MERGE INTO {silver_object} t
            USING {temp_view_name} s
            ON t.observation_id = s.observation_id
            WHEN MATCHED AND {material_change_condition}
              THEN UPDATE SET {update_assignments}
            WHEN NOT MATCHED
              THEN INSERT ({insert_columns}) VALUES ({insert_values})
            WHEN NOT MATCHED BY SOURCE
              THEN DELETE
            """
        )
    finally:
        spark.catalog.dropTempView(temp_view_name)


def _normalized_valid_snapshot(normalized_df: DataFrame) -> tuple[DataFrame, DataFrame]:
    with_reason = normalized_df.withColumn("rejection_reason", _rejection_reason_column())
    valid_rows = with_reason.where(F.col("rejection_reason").isNull()).drop("rejection_reason")
    rejected_rows = with_reason.where(F.col("rejection_reason").isNotNull())

    valid_with_hash = valid_rows.withColumn("_payload_hash", _material_payload_hash())
    window = Window.partitionBy("observation_id").orderBy(
        F.col("ingested_at").desc(),
        F.col("_payload_hash").desc(),
    )
    deduped = (
        valid_with_hash.withColumn("_rn", F.row_number().over(window))
        .where(F.col("_rn") == 1)
        .drop("_rn")
        .withColumnRenamed("_payload_hash", "silver_record_hash")
        .withColumn("silver_normalized_at", F.current_timestamp())
    )
    return deduped, rejected_rows


def load_silver_observations(
    spark: SparkSession,
    bronze_object: str,
    silver_object: str,
) -> SilverLoadResult:
    """Synchronize Silver from the full Bronze snapshot of structurally valid observations.

    Safety contract:
    - The delete-capable path owns the Bronze read and always reads the full table
      identified by bronze_object.
    - The public API does not accept caller-supplied DataFrames, preventing
      accidental filtered-input deletes.
    """

    if not spark.catalog.tableExists(bronze_object):
        raise ValueError(f"Bronze source table does not exist: {bronze_object}")

    bronze_df = spark.table(bronze_object)
    if not isinstance(bronze_df, DataFrame):
        raise ValueError("Bronze source read did not produce a Spark DataFrame")
    required = ["observation_id", "company_id", "metric_id", "period_id", "value", "ingested_at"]
    if not _required_columns_present(bronze_df, required):
        missing = sorted(set(required) - set(bronze_df.columns))
        raise ValueError(f"Bronze source is missing required columns: {', '.join(missing)}")

    bronze_input_rows = bronze_df.count()
    normalized_df = _normalize_bronze_rows(bronze_df)
    valid_deduped_df, rejected_df = _normalized_valid_snapshot(normalized_df)

    # NOTE: Slice 2 intentionally computes observability metrics with multiple actions.
    # Spark action count optimization is deferred to a later slice.
    bronze_rejected_rows_total = rejected_df.count()
    by_reason_rows = rejected_df.groupBy("rejection_reason").count().collect()
    bronze_rejected_rows_by_reason = {
        row["rejection_reason"]: row["count"] for row in by_reason_rows
    }

    bronze_structurally_valid_rows = bronze_input_rows - bronze_rejected_rows_total
    silver_batch_rows_after_dedup = valid_deduped_df.count()
    bronze_distinct_valid_observation_ids = silver_batch_rows_after_dedup

    if not spark.catalog.tableExists(silver_object):
        valid_deduped_df.select(
            "observation_id",
            "company_id",
            "metric_id",
            "period_id",
            "value",
            "ingested_at",
            "silver_record_hash",
            "silver_normalized_at",
        ).write.format("delta").mode("overwrite").saveAsTable(silver_object)

        silver_final_row_count = spark.table(silver_object).count()
        reconciliation_delta = silver_final_row_count - bronze_distinct_valid_observation_ids
        return SilverLoadResult(
            silver_object=silver_object,
            bronze_input_rows=bronze_input_rows,
            bronze_structurally_valid_rows=bronze_structurally_valid_rows,
            bronze_rejected_rows_total=bronze_rejected_rows_total,
            bronze_rejected_rows_by_reason=bronze_rejected_rows_by_reason,
            silver_batch_rows_after_dedup=silver_batch_rows_after_dedup,
            inserted_rows=silver_batch_rows_after_dedup,
            updated_rows=0,
            silver_deleted_rows=0,
            silver_final_row_count=silver_final_row_count,
            bronze_distinct_valid_observation_ids=bronze_distinct_valid_observation_ids,
            reconciliation_delta=reconciliation_delta,
        )

    existing_df = spark.table(silver_object).alias("t")
    source_df = valid_deduped_df.alias("s")
    material_change_condition = _material_change_condition_sql(target_alias="t", source_alias="s")

    inserted_rows = source_df.join(
        existing_df.select("observation_id"), on="observation_id", how="left_anti"
    ).count()
    updated_rows = (
        existing_df.join(source_df, on="observation_id", how="inner")
        .where(F.expr(material_change_condition))
        .count()
    )
    silver_deleted_rows = (
        existing_df.select("observation_id")
        .join(source_df.select("observation_id"), on="observation_id", how="left_anti")
        .count()
    )

    _merge_into_silver_table(
        spark=spark,
        source_df=valid_deduped_df.select(
            "observation_id",
            "company_id",
            "metric_id",
            "period_id",
            "value",
            "ingested_at",
            "silver_record_hash",
            "silver_normalized_at",
        ),
        silver_object=silver_object,
        material_change_condition=material_change_condition,
    )

    silver_final_row_count = spark.table(silver_object).count()
    reconciliation_delta = silver_final_row_count - bronze_distinct_valid_observation_ids
    return SilverLoadResult(
        silver_object=silver_object,
        bronze_input_rows=bronze_input_rows,
        bronze_structurally_valid_rows=bronze_structurally_valid_rows,
        bronze_rejected_rows_total=bronze_rejected_rows_total,
        bronze_rejected_rows_by_reason=bronze_rejected_rows_by_reason,
        silver_batch_rows_after_dedup=silver_batch_rows_after_dedup,
        inserted_rows=inserted_rows,
        updated_rows=updated_rows,
        silver_deleted_rows=silver_deleted_rows,
        silver_final_row_count=silver_final_row_count,
        bronze_distinct_valid_observation_ids=bronze_distinct_valid_observation_ids,
        reconciliation_delta=reconciliation_delta,
    )