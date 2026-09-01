"""Consumption-oriented Gold news projection."""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


@dataclass(frozen=True)
class NewsGoldLoadResult:
    gold_object: str
    silver_rows: int
    enrichment_rows: int
    gold_rows: int
    reconciliation_delta: int


def load_gold_news(spark: SparkSession, silver_object: str, enrichment_object: str, gold_object: str) -> NewsGoldLoadResult:
    silver = spark.table(silver_object)
    enrichment = spark.table(enrichment_object)
    latest = (enrichment.where(F.col("enrichment_status") == "succeeded").withColumn("_rn", F.row_number().over(Window.partitionBy("article_id").orderBy(F.col("enriched_at").desc()))).where("_rn=1").drop("_rn"))
    gold = silver.join(latest, "article_id", "left").select("article_id", "source", "source_url", "title", "published_at", "relevant_company_ids", "summary", "categories", "enrichment_status", "model_name", "prompt_version", "enriched_at")
    gold.write.format("delta").mode("overwrite").saveAsTable(gold_object)
    count = spark.table(gold_object).count()
    return NewsGoldLoadResult(gold_object, silver.count(), enrichment.count(), count, count - silver.count())