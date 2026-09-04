"""Deterministic normalization and deduplication for Bronze news."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

from vigie_databricks.news_bronze import normalize_url


SILVER_COLUMNS = ["article_id", "source", "source_type", "company_id", "source_article_id", "source_url", "title", "description", "published_at", "fetched_at", "content_hash", "silver_record_hash", "silver_normalized_at"]


@dataclass(frozen=True)
class NewsSilverLoadResult:
    silver_object: str
    bronze_input_rows: int
    rejected_rows: int
    silver_rows: int
    inserted_rows: int
    updated_rows: int
    reconciliation_delta: int


def build_silver(spark, bronze_object: str):
    bronze = spark.table(bronze_object)
    if "source_type" not in bronze.columns:
        bronze = bronze.withColumn("source_type", F.lit("external_context"))
    if "company_id" not in bronze.columns:
        bronze = bronze.withColumn("company_id", F.lit(None).cast("string"))
    normalized = (bronze.select("article_id", "source", "source_type", "company_id", "source_article_id", "source_url", F.trim("title_raw").alias("title"), F.trim("description_raw").alias("description"), F.expr("try_to_timestamp(published_at_iso)").alias("published_at"), F.expr("try_to_timestamp(fetched_at)").alias("fetched_at"), "content_hash")
        .withColumn("source_url", F.lower(F.regexp_replace(F.regexp_replace(F.trim("source_url"), r"#.*$", ""), r"/$", "")))
        .withColumn("_rejection", F.when(F.col("article_id").isNull() | (F.length("article_id") == 0), "missing_article_id").when(F.col("source_url").isNull() | (F.length("source_url") == 0), "missing_source_url").when(F.col("title").isNull() | (F.length("title") == 0), "missing_title"))
    )
    rejected = normalized.where(F.col("_rejection").isNotNull()).count()
    valid = normalized.where(F.col("_rejection").isNull()).drop("_rejection")
    hash_expr = F.sha2(F.concat_ws("||", *[F.coalesce(F.col(c).cast("string"), F.lit("<NULL>")) for c in ["article_id", "source", "source_type", "company_id", "source_url", "title", "description", "published_at"]]), 256)
    valid = valid.withColumn("silver_record_hash", hash_expr).withColumn("silver_normalized_at", F.current_timestamp())
    window = Window.partitionBy("article_id").orderBy(F.col("fetched_at").desc(), F.col("silver_record_hash").desc())
    return valid.withColumn("_rn", F.row_number().over(window)).where("_rn=1").drop("_rn") .select(*SILVER_COLUMNS), rejected


def load_silver_news(spark: SparkSession, bronze_object: str, silver_object: str) -> NewsSilverLoadResult:
    bronze_input = spark.table(bronze_object).count()
    source, rejected = build_silver(spark, bronze_object)
    rows = source.count()
    if not spark.catalog.tableExists(silver_object):
        source.write.format("delta").mode("overwrite").saveAsTable(silver_object)
        inserted, updated = rows, 0
    else:
        existing = spark.table(silver_object).select("article_id", "silver_record_hash").alias("t")
        incoming = source.alias("s")
        inserted = incoming.join(existing, "article_id", "left_anti").count()
        updated = existing.join(incoming, "article_id").where(F.expr("NOT (t.silver_record_hash <=> s.silver_record_hash)")).count()
        view = f"vigie_news_silver_{uuid4().hex}"
        source.createOrReplaceTempView(view)
        try:
            columns = ", ".join(SILVER_COLUMNS); values = ", ".join(f"s.{c}" for c in SILVER_COLUMNS); assignments = ", ".join(f"{c}=s.{c}" for c in SILVER_COLUMNS)
            spark.sql(f"MERGE INTO {silver_object} t USING {view} s ON t.article_id=s.article_id WHEN MATCHED AND NOT (t.silver_record_hash <=> s.silver_record_hash) THEN UPDATE SET {assignments} WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values}) WHEN NOT MATCHED BY SOURCE THEN DELETE")
        finally:
            spark.catalog.dropTempView(view)
    final = spark.table(silver_object).count()
    return NewsSilverLoadResult(silver_object, bronze_input, rejected, rows, inserted, updated, final - rows)