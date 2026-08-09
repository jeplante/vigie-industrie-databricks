"""Slice 3 Gold deterministic monitoring/comparison helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import uuid4

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F


MATERIAL_COLUMNS = [
    "current_period_id",
    "current_value",
    "previous_period_id",
    "previous_value",
    "change_value",
    "change_pct",
    "direction",
    "gold_record_hash",
]


@dataclass(frozen=True)
class GoldLoadResult:
    """Operational counters for one Gold synchronization execution."""

    gold_object: str
    silver_input_rows: int
    silver_distinct_company_metric_keys: int
    gold_batch_rows: int
    inserted_rows: int
    updated_rows: int
    deleted_rows: int
    gold_final_row_count: int
    reconciliation_delta: int


def _required_columns_present(df: DataFrame, required: Iterable[str]) -> bool:
    available = set(df.columns)
    return all(column in available for column in required)


def _material_payload_hash() -> F.Column:
    parts = [F.coalesce(F.col(column).cast("string"), F.lit("<NULL>")) for column in MATERIAL_COLUMNS[:-1]]
    return F.sha2(F.concat_ws("||", *parts), 256)


def _material_change_condition_sql(target_alias: str = "t", source_alias: str = "s") -> str:
    comparisons = [
        f"{target_alias}.{column} <=> {source_alias}.{column}" for column in MATERIAL_COLUMNS
    ]
    return "NOT (" + " AND ".join(comparisons) + ")"


def _resolve_same_period_duplicates(silver_df: DataFrame) -> DataFrame:
    """Keep one deterministic row per company+metric+period.

    Priority order:
    1) greatest ingested_at
    2) greatest observation_id when ingested_at ties
    """

    window = Window.partitionBy("company_id", "metric_id", "period_id").orderBy(
        F.col("ingested_at").desc(),
        F.col("observation_id").desc(),
    )
    return (
        silver_df.withColumn("_rn_same_period", F.row_number().over(window))
        .where(F.col("_rn_same_period") == 1)
        .drop("_rn_same_period")
    )


def _validate_supported_silver_source(spark: SparkSession, silver_object: str) -> None:
    """Fail closed unless the source is a persisted Delta table relation."""

    try:
        table = spark.catalog.getTable(silver_object)
    except Exception as exc:  # pragma: no cover - backend-specific lookup failures
        raise ValueError(
            "Silver source relation cannot be validated as a persisted full snapshot table"
        ) from exc

    table_type = (table.tableType or "").upper()
    if table.isTemporary or "VIEW" in table_type:
        raise ValueError(
            "Silver source must be a persisted full snapshot table; views are not supported"
        )

    if "TABLE" not in table_type and table_type not in {"MANAGED", "EXTERNAL"}:
        raise ValueError(
            f"Unsupported Silver source relation type for delete-capable sync: {table_type or '<unknown>'}"
        )

    detail = spark.sql(f"DESCRIBE DETAIL {silver_object}").collect()
    if not detail:
        raise ValueError("Silver source relation details are unavailable")
    source_format = str(detail[0].asDict().get("format", "")).lower()
    if source_format != "delta":
        raise ValueError(
            f"Silver source must be a Delta table for delete-capable sync, got: {source_format or '<unknown>'}"
        )


def _latest_delta_version(spark: SparkSession, object_name: str) -> int:
    row = spark.sql(f"DESCRIBE HISTORY {object_name} LIMIT 1").collect()[0]
    return int(row["version"])


def _to_int_metric(metrics: dict[str, Any], key: str) -> int:
    value = metrics.get(key)
    return int(value) if value is not None else 0


def _merge_write_metrics(
    spark: SparkSession,
    object_name: str,
    min_version_exclusive: int,
) -> tuple[int, int, int]:
    history_rows = (
        spark.sql(f"DESCRIBE HISTORY {object_name}")
        .where(F.col("version") > F.lit(min_version_exclusive))
        .orderBy(F.col("version").asc())
        .collect()
    )
    for row in history_rows:
        if row["operation"] != "MERGE":
            continue
        metrics = row["operationMetrics"] or {}
        inserted = _to_int_metric(metrics, "numTargetRowsInserted")
        updated = _to_int_metric(metrics, "numTargetRowsUpdated")
        deleted = _to_int_metric(metrics, "numTargetRowsDeleted")
        return inserted, updated, deleted
    raise ValueError("MERGE operation metrics were not found for the executed Gold synchronization")


def _build_gold_snapshot(silver_df: DataFrame) -> DataFrame:
    resolved = _resolve_same_period_duplicates(
        silver_df.select("observation_id", "company_id", "metric_id", "period_id", "value", "ingested_at")
    )

    enriched = resolved.withColumn("_period_year", F.substring("period_id", 1, 4).cast("int")).withColumn(
        "_period_quarter", F.substring("period_id", 6, 1).cast("int")
    )

    window = Window.partitionBy("company_id", "metric_id").orderBy(
        F.col("_period_year").desc(),
        F.col("_period_quarter").desc(),
    )

    latest_with_previous = (
        enriched.withColumn("_seq", F.row_number().over(window))
        .withColumn("_previous_period_id", F.lead("period_id").over(window))
        .withColumn("_previous_value", F.lead("value").over(window))
        .where(F.col("_seq") == 1)
        .drop("_seq", "_period_year", "_period_quarter", "observation_id", "period_id", "value", "ingested_at")
        .withColumnRenamed("_previous_period_id", "previous_period_id")
        .withColumnRenamed("_previous_value", "previous_value")
    )

    # Re-attach current values after deterministic latest-period selection.
    current_rows = (
        enriched.withColumn("_seq", F.row_number().over(window))
        .where(F.col("_seq") == 1)
        .select(
            "company_id",
            "metric_id",
            F.col("period_id").alias("current_period_id"),
            F.col("value").alias("current_value"),
        )
    )

    base = latest_with_previous.join(current_rows, on=["company_id", "metric_id"], how="inner")

    with_change = (
        base.withColumn(
            "change_value",
            F.when(F.col("previous_value").isNull(), F.lit(None).cast("double")).otherwise(
                F.col("current_value") - F.col("previous_value")
            ),
        )
        .withColumn(
            "change_pct",
            F.when(F.col("previous_value").isNull(), F.lit(None).cast("double"))
            .when(F.col("previous_value") != F.lit(0.0), (F.col("current_value") - F.col("previous_value")) / F.abs(F.col("previous_value")))
            .when((F.col("previous_value") == F.lit(0.0)) & (F.col("current_value") == F.lit(0.0)), F.lit(0.0))
            .otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            "direction",
            F.when(F.col("previous_value").isNull(), F.lit(None).cast("string"))
            .when(F.col("change_value") > F.lit(0.0), F.lit("up"))
            .when(F.col("change_value") < F.lit(0.0), F.lit("down"))
            .otherwise(F.lit("neutral")),
        )
    )

    return (
        with_change.withColumn("gold_record_hash", _material_payload_hash())
        .withColumn("computed_at", F.current_timestamp())
        .select(
            "company_id",
            "metric_id",
            "current_period_id",
            "current_value",
            "previous_period_id",
            "previous_value",
            "change_value",
            "change_pct",
            "direction",
            "gold_record_hash",
            "computed_at",
        )
    )


def _merge_into_gold_table(
    spark: SparkSession,
    source_df: DataFrame,
    gold_object: str,
    material_change_condition: str,
) -> None:
    temp_view_name = f"vigie_gold_merge_source_{uuid4().hex}"
    source_df.createOrReplaceTempView(temp_view_name)
    try:
        columns = [
            "company_id",
            "metric_id",
            "current_period_id",
            "current_value",
            "previous_period_id",
            "previous_value",
            "change_value",
            "change_pct",
            "direction",
            "gold_record_hash",
            "computed_at",
        ]
        update_assignments = ", ".join([f"{column} = s.{column}" for column in columns])
        insert_columns = ", ".join(columns)
        insert_values = ", ".join([f"s.{column}" for column in columns])

        spark.sql(
            f"""
            MERGE INTO {gold_object} t
            USING {temp_view_name} s
            ON t.company_id = s.company_id AND t.metric_id = s.metric_id
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


def load_gold_observations(
    spark: SparkSession,
    silver_object: str,
    gold_object: str,
) -> GoldLoadResult:
    """Synchronize Gold from the full Silver snapshot.

    Safety contract:
    - The delete-capable path owns the Silver read and always reads the full table
      identified by silver_object.
    - The public API does not accept caller-supplied DataFrames, preventing
      accidental filtered-input deletes.
    """

    if not spark.catalog.tableExists(silver_object):
        raise ValueError(f"Silver source table does not exist: {silver_object}")

    _validate_supported_silver_source(spark, silver_object)

    silver_df = spark.table(silver_object)
    if not isinstance(silver_df, DataFrame):
        raise ValueError("Silver source read did not produce a Spark DataFrame")

    required = ["observation_id", "company_id", "metric_id", "period_id", "value", "ingested_at"]
    if not _required_columns_present(silver_df, required):
        missing = sorted(set(required) - set(silver_df.columns))
        raise ValueError(f"Silver source is missing required columns: {', '.join(missing)}")

    silver_input_rows = silver_df.count()
    source_df = _build_gold_snapshot(silver_df)

    gold_batch_rows = source_df.count()
    silver_distinct_company_metric_keys = gold_batch_rows

    if not spark.catalog.tableExists(gold_object):
        source_df.write.format("delta").mode("overwrite").saveAsTable(gold_object)
        gold_final_row_count = spark.table(gold_object).count()
        reconciliation_delta = gold_final_row_count - silver_distinct_company_metric_keys
        return GoldLoadResult(
            gold_object=gold_object,
            silver_input_rows=silver_input_rows,
            silver_distinct_company_metric_keys=silver_distinct_company_metric_keys,
            gold_batch_rows=gold_batch_rows,
            inserted_rows=gold_batch_rows,
            updated_rows=0,
            deleted_rows=0,
            gold_final_row_count=gold_final_row_count,
            reconciliation_delta=reconciliation_delta,
        )

    material_change_condition = _material_change_condition_sql(target_alias="t", source_alias="s")

    pre_merge_version = _latest_delta_version(spark, gold_object)

    _merge_into_gold_table(
        spark=spark,
        source_df=source_df,
        gold_object=gold_object,
        material_change_condition=material_change_condition,
    )

    inserted_rows, updated_rows, deleted_rows = _merge_write_metrics(
        spark=spark,
        object_name=gold_object,
        min_version_exclusive=pre_merge_version,
    )

    gold_final_row_count = spark.table(gold_object).count()
    reconciliation_delta = gold_final_row_count - silver_distinct_company_metric_keys
    return GoldLoadResult(
        gold_object=gold_object,
        silver_input_rows=silver_input_rows,
        silver_distinct_company_metric_keys=silver_distinct_company_metric_keys,
        gold_batch_rows=gold_batch_rows,
        inserted_rows=inserted_rows,
        updated_rows=updated_rows,
        deleted_rows=deleted_rows,
        gold_final_row_count=gold_final_row_count,
        reconciliation_delta=reconciliation_delta,
    )