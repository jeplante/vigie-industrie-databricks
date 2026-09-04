from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from vigie_databricks.news_ai import load_news_ai
from vigie_databricks.news_bronze import load_bronze_news
from vigie_databricks.news_gold import load_gold_news
from vigie_databricks.news_silver import load_silver_news


pytestmark = pytest.mark.databricks_connect


@pytest.fixture(scope="session")
def connect_spark():
    try:
        from databricks.connect import DatabricksSession
    except Exception:
        pytest.skip("Databricks Connect is not installed in the current environment.")
    builder = DatabricksSession.builder
    profile = os.environ.get("DATABRICKS_CONNECT_PROFILE")
    cluster_id = os.environ.get("DATABRICKS_CLUSTER_ID")
    builder = builder.profile(profile) if profile else builder
    return builder.clusterId(cluster_id).getOrCreate() if cluster_id else builder.serverless(True).getOrCreate()


def test_news_delta_pipeline_with_fake_enrichment(connect_spark, monkeypatch):
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    prefix = uuid4().hex
    bronze = f"{context['catalog']}.{context['schema']}.vigie_bronze_news_{prefix}"
    silver = f"{context['catalog']}.{context['schema']}.vigie_silver_news_{prefix}"
    enrichment = f"{context['catalog']}.{context['schema']}.vigie_news_ai_enrichment_{prefix}"
    gold = f"{context['catalog']}.{context['schema']}.vigie_gold_news_{prefix}"
    fixture = Path(__file__).parent / "fixtures" / "slice6_news_rss.xml"

    first_bronze = load_bronze_news(connect_spark, "fixture", "", str(fixture), bronze)
    first_silver = load_silver_news(connect_spark, bronze, silver)

    def fake_model(row, model_name, known_company_ids):
        return {"summary": "Fixture summary", "categories": ["other"], "relevant_company_ids": []}, {"total_tokens": 1}

    monkeypatch.setattr("vigie_databricks.news_ai.call_model", fake_model)
    first_ai = load_news_ai(connect_spark, silver, enrichment, "databricks-gpt-oss-20b")
    first_gold = load_gold_news(connect_spark, silver, enrichment, gold)
    second_ai = load_news_ai(connect_spark, silver, enrichment, "databricks-gpt-oss-20b")

    assert first_bronze.inserted_rows == 2
    assert first_silver.silver_rows == 2
    assert first_silver.rejected_rows == 0
    assert first_ai.model_calls == 2
    assert first_ai.succeeded_rows == 2
    assert first_gold.gold_rows == 2
    assert first_gold.reconciliation_delta == 0
    assert second_ai.model_calls == 0
    assert connect_spark.table(gold).count() == 2


def test_atom_bronze_is_idempotent(connect_spark):
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze = f"{context['catalog']}.{context['schema']}.vigie_bronze_news_{uuid4().hex}"
    fixture = Path(__file__).parent / "fixtures" / "slice7_statcan_atom.xml"

    first = load_bronze_news(
        connect_spark,
        "fixture",
        "",
        str(fixture),
        bronze,
        source="statcan_manufacturing",
        max_articles=25,
    )
    second = load_bronze_news(
        connect_spark,
        "fixture",
        "",
        str(fixture),
        bronze,
        source="statcan_manufacturing",
        max_articles=25,
    )

    assert first.input_rows == 2
    assert first.inserted_rows == 2
    assert first.updated_rows == 0
    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.final_row_count == 2


@pytest.mark.skipif(
    os.environ.get("RUN_SLICE7_LIVE") != "1",
    reason="Set RUN_SLICE7_LIVE=1 for the bounded, no-model live acceptance.",
)
def test_live_statcan_bronze_is_bounded_and_idempotent(connect_spark):
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze = f"{context['catalog']}.{context['schema']}.vigie_bronze_news_{uuid4().hex}"
    sources = json.dumps([
        {
            "source_id": "statcan_manufacturing",
            "url": "https://www150.statcan.gc.ca/n1/rss/dai-quo/16-eng.atom",
            "enabled": True,
        },
        {
            "source_id": "statcan_international_trade",
            "url": "https://www150.statcan.gc.ca/n1/rss/dai-quo/12-eng.atom",
            "enabled": True,
        },
    ])

    first = load_bronze_news(
        connect_spark,
        "live",
        "",
        None,
        bronze,
        max_articles=25,
        sources_json=sources,
    )
    second = load_bronze_news(
        connect_spark,
        "live",
        "",
        None,
        bronze,
        max_articles=25,
        sources_json=sources,
    )

    assert 1 <= first.input_rows <= 50
    assert first.sources_succeeded == 2
    assert first.sources_failed == 0
    assert first.inserted_rows == first.input_rows
    assert first.updated_rows == 0
    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.final_row_count == first.final_row_count
