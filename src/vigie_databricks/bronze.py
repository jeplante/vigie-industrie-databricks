"""Slice 1 Bronze Delta ingestion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F


@dataclass(frozen=True)
class BronzeLoadResult:
    """Operational counters for one Bronze load execution."""

    bronze_object: str
    input_rows: int
    batch_rows_after_dedup: int
    inserted_rows: int
    updated_rows: int
    final_row_count: int


MATERIAL_COLUMNS = ["company_id", "metric_id", "period_id", "value"]


def _material_payload_hash() -> F.Column:
    parts = [F.coalesce(F.col(column).cast("string"), F.lit("<NULL>")) for column in MATERIAL_COLUMNS]
    return F.sha2(F.concat_ws("||", *parts), 256)


def _material_change_condition_sql(target_alias: str = "t", source_alias: str = "s") -> str:
    comparisons = [
        f"{target_alias}.{column} <=> {source_alias}.{column}" for column in MATERIAL_COLUMNS
    ]
    return "NOT (" + " AND ".join(comparisons) + ")"


def _merge_into_bronze_table(
    spark: SparkSession,
    source_df: DataFrame,
    bronze_object: str,
    material_change_condition: str,
) -> None:
    temp_view_name = f"vigie_bronze_merge_source_{uuid4().hex}"
    source_df.createOrReplaceTempView(temp_view_name)
    try:
        columns = ["observation_id", "company_id", "metric_id", "period_id", "value", "ingested_at"]
        update_assignments = ", ".join([f"{column} = s.{column}" for column in columns])
        insert_columns = ", ".join(columns)
        insert_values = ", ".join([f"s.{column}" for column in columns])

        spark.sql(
            f"""
            MERGE INTO {bronze_object} t
            USING {temp_view_name} s
            ON t.observation_id = s.observation_id
            WHEN MATCHED AND {material_change_condition}
              THEN UPDATE SET {update_assignments}
            WHEN NOT MATCHED
              THEN INSERT ({insert_columns}) VALUES ({insert_values})
            """
        )
    finally:
        spark.catalog.dropTempView(temp_view_name)


def _normalize_rows(spark: SparkSession, rows: Iterable[dict]) -> DataFrame:
    base_df = spark.createDataFrame(rows)

    if "ingested_at" not in base_df.columns:
        base_df = base_df.withColumn("ingested_at", F.current_timestamp())
    else:
        base_df = base_df.withColumn("ingested_at", F.to_timestamp("ingested_at"))

    required = [
        "observation_id",
        "company_id",
        "metric_id",
        "period_id",
        "value",
        "ingested_at",
    ]
    missing = [column for column in required if column not in base_df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    normalized = base_df.select(*required)
    normalized = normalized.withColumn("value", F.col("value").cast("double"))
    normalized = normalized.withColumn("_payload_hash", _material_payload_hash())

    window = Window.partitionBy("observation_id").orderBy(
        F.col("ingested_at").desc(),
        F.col("_payload_hash").desc(),
    )
    deduped = (
        normalized.withColumn("_rn", F.row_number().over(window))
        .where(F.col("_rn") == 1)
        .drop("_rn", "_payload_hash")
    )

    return deduped


def load_bronze_observations(
    spark: SparkSession,
    rows: Iterable[dict],
    bronze_object: str,
) -> BronzeLoadResult:
    """Load an observation batch into a Bronze Delta table with idempotent merge behavior."""

    rows_list = list(rows)
    if not rows_list:
        raise ValueError("rows must contain at least one observation")

    deduped = _normalize_rows(spark=spark, rows=rows_list)
    input_rows = spark.createDataFrame(rows_list).count()
    dedup_count = deduped.count()

    if not spark.catalog.tableExists(bronze_object):
        deduped.write.format("delta").mode("overwrite").saveAsTable(bronze_object)
        final_count = spark.table(bronze_object).count()
        return BronzeLoadResult(
            bronze_object=bronze_object,
            input_rows=input_rows,
            batch_rows_after_dedup=dedup_count,
            inserted_rows=dedup_count,
            updated_rows=0,
            final_row_count=final_count,
        )

    existing_df = spark.table(bronze_object).select("observation_id").distinct()
    inserted_rows = deduped.join(existing_df, on="observation_id", how="left_anti").count()

    current_df = spark.table(bronze_object).alias("t")
    source_df = deduped.alias("s")
    material_change_condition = _material_change_condition_sql(target_alias="t", source_alias="s")
    updated_rows = (
        current_df.join(source_df, on="observation_id", how="inner")
        .where(F.expr(material_change_condition))
        .count()
    )

    _merge_into_bronze_table(
        spark=spark,
        source_df=deduped,
        bronze_object=bronze_object,
        material_change_condition=material_change_condition,
    )

    final_count = spark.table(bronze_object).count()
    return BronzeLoadResult(
        bronze_object=bronze_object,
        input_rows=input_rows,
        batch_rows_after_dedup=dedup_count,
        inserted_rows=inserted_rows,
        updated_rows=updated_rows,
        final_row_count=final_count,
    )