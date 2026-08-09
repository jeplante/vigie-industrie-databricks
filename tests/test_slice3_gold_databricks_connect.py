from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest

from vigie_databricks.bronze import load_bronze_observations
from vigie_databricks.gold import load_gold_observations
from vigie_databricks.silver import load_silver_observations


pytestmark = pytest.mark.databricks_connect


@pytest.fixture(scope="session")
def connect_spark():
    try:
        from databricks.connect import DatabricksSession
    except Exception:
        pytest.skip("Databricks Connect is not installed in the current environment.")

    try:
        builder = DatabricksSession.builder

        profile = os.environ.get("DATABRICKS_CONNECT_PROFILE")
        if profile:
            builder = builder.profile(profile)

        cluster_id = os.environ.get("DATABRICKS_CLUSTER_ID")
        if cluster_id:
            spark = builder.clusterId(cluster_id).getOrCreate()
        else:
            spark = builder.serverless(True).getOrCreate()
    except Exception as exc:
        pytest.fail(
            "Databricks Connect dependency is installed but the remote session could not be created. "
            f"Check Databricks auth/profile/serverless compatibility. Original error: {exc}"
        )

    return spark


def _objects(connect_spark, prefix: str) -> tuple[str, str, str]:
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze = f"{context['catalog']}.{context['schema']}.vigie_bronze_{prefix}_{uuid4().hex}"
    silver = f"{context['catalog']}.{context['schema']}.vigie_silver_{prefix}_{uuid4().hex}"
    gold = f"{context['catalog']}.{context['schema']}.vigie_gold_{prefix}_{uuid4().hex}"
    return bronze, silver, gold


def test_gold_same_period_resolution_non_contiguous_previous_and_rerun(connect_spark) -> None:
    bronze_object, silver_object, gold_object = _objects(connect_spark, "s3_core")

    base = datetime.now(UTC)
    bronze_rows = [
        {
            "observation_id": "obs-2026q2-old",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 100.0,
            "ingested_at": base.isoformat(),
        },
        {
            "observation_id": "obs-2026q2-new",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 120.0,
            "ingested_at": (base + timedelta(minutes=5)).isoformat(),
        },
        {
            "observation_id": "obs-2025q4",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2025Q4",
            "value": 90.0,
            "ingested_at": (base - timedelta(days=90)).isoformat(),
        },
        {
            "observation_id": "obs-only",
            "company_id": "C2",
            "metric_id": "margin",
            "period_id": "2026Q2",
            "value": 7.0,
            "ingested_at": base.isoformat(),
        },
        {
            "observation_id": "obs-zero-prev",
            "company_id": "C3",
            "metric_id": "ratio",
            "period_id": "2026Q2",
            "value": 5.0,
            "ingested_at": base.isoformat(),
        },
        {
            "observation_id": "obs-zero-prev-older",
            "company_id": "C3",
            "metric_id": "ratio",
            "period_id": "2025Q4",
            "value": 0.0,
            "ingested_at": (base - timedelta(days=90)).isoformat(),
        },
        {
            "observation_id": "obs-tie-a",
            "company_id": "C4",
            "metric_id": "quality",
            "period_id": "2026Q2",
            "value": 1.0,
            "ingested_at": (base + timedelta(minutes=7)).isoformat(),
        },
        {
            "observation_id": "obs-tie-z",
            "company_id": "C4",
            "metric_id": "quality",
            "period_id": "2026Q2",
            "value": 2.0,
            "ingested_at": (base + timedelta(minutes=7)).isoformat(),
        },
        {
            "observation_id": "obs-tie-prev",
            "company_id": "C4",
            "metric_id": "quality",
            "period_id": "2025Q4",
            "value": 0.0,
            "ingested_at": (base - timedelta(days=90)).isoformat(),
        },
    ]
    load_bronze_observations(connect_spark, bronze_rows, bronze_object)
    load_silver_observations(connect_spark, bronze_object, silver_object)

    first = load_gold_observations(connect_spark, silver_object, gold_object)
    second = load_gold_observations(connect_spark, silver_object, gold_object)

    assert first.inserted_rows == 4
    assert first.updated_rows == 0
    assert first.deleted_rows == 0
    assert first.reconciliation_delta == 0
    assert first.gold_final_row_count == first.silver_distinct_company_metric_keys

    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.deleted_rows == 0
    assert second.reconciliation_delta == 0

    rows = connect_spark.table(gold_object).where("company_id = 'C1' AND metric_id = 'revenue'").collect()
    assert len(rows) == 1
    row = rows[0]
    assert row["current_period_id"] == "2026Q2"
    assert row["current_value"] == 120.0
    assert row["previous_period_id"] == "2025Q4"
    assert row["previous_value"] == 90.0
    assert row["change_value"] == 30.0
    assert row["change_pct"] == pytest.approx((120.0 - 90.0) / 90.0)
    assert row["direction"] == "up"

    one_period = connect_spark.table(gold_object).where("company_id = 'C2' AND metric_id = 'margin'").collect()[0]
    assert one_period["current_period_id"] == "2026Q2"
    assert one_period["previous_period_id"] is None
    assert one_period["previous_value"] is None
    assert one_period["change_value"] is None
    assert one_period["change_pct"] is None
    assert one_period["direction"] is None

    zero_prev = connect_spark.table(gold_object).where("company_id = 'C3' AND metric_id = 'ratio'").collect()[0]
    assert zero_prev["current_period_id"] == "2026Q2"
    assert zero_prev["previous_period_id"] == "2025Q4"
    assert zero_prev["previous_value"] == 0.0
    assert zero_prev["current_value"] == 5.0
    assert zero_prev["change_value"] == 5.0
    assert zero_prev["change_pct"] is None
    assert zero_prev["direction"] == "up"

    tie_break = connect_spark.table(gold_object).where("company_id = 'C4' AND metric_id = 'quality'").collect()[0]
    assert tie_break["current_period_id"] == "2026Q2"
    assert tie_break["current_value"] == 2.0
    assert tie_break["previous_period_id"] == "2025Q4"


def test_gold_changed_current_changed_previous_and_delete(connect_spark) -> None:
    bronze_object, silver_object, gold_object = _objects(connect_spark, "s3_mut")
    base = datetime.now(UTC)

    initial = [
        {
            "observation_id": "m-2026q2",
            "company_id": "M1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 100.0,
            "ingested_at": base.isoformat(),
        },
        {
            "observation_id": "m-2025q4",
            "company_id": "M1",
            "metric_id": "revenue",
            "period_id": "2025Q4",
            "value": 80.0,
            "ingested_at": (base - timedelta(days=90)).isoformat(),
        },
        {
            "observation_id": "m-delete",
            "company_id": "M2",
            "metric_id": "margin",
            "period_id": "2026Q2",
            "value": 11.0,
            "ingested_at": base.isoformat(),
        },
    ]
    load_bronze_observations(connect_spark, initial, bronze_object)
    load_silver_observations(connect_spark, bronze_object, silver_object)
    first = load_gold_observations(connect_spark, silver_object, gold_object)
    assert first.inserted_rows == 2

    # Changed-current behavior: latest period value changes.
    changed_current = [
        {
            "observation_id": "m-2026q2",
            "company_id": "M1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 130.0,
            "ingested_at": (base + timedelta(minutes=5)).isoformat(),
        }
    ]
    load_bronze_observations(connect_spark, changed_current, bronze_object)
    load_silver_observations(connect_spark, bronze_object, silver_object)
    second = load_gold_observations(connect_spark, silver_object, gold_object)
    assert second.inserted_rows == 0
    assert second.updated_rows >= 1
    assert second.deleted_rows == 0
    assert second.reconciliation_delta == 0

    after_current = connect_spark.table(gold_object).where("company_id='M1' AND metric_id='revenue'").collect()[0]
    assert after_current["current_value"] == 130.0
    assert after_current["previous_value"] == 80.0
    assert after_current["change_value"] == 50.0

    # Changed-previous behavior: previous available period value changes.
    changed_previous = [
        {
            "observation_id": "m-2025q4",
            "company_id": "M1",
            "metric_id": "revenue",
            "period_id": "2025Q4",
            "value": 70.0,
            "ingested_at": (base + timedelta(minutes=6)).isoformat(),
        }
    ]
    load_bronze_observations(connect_spark, changed_previous, bronze_object)
    load_silver_observations(connect_spark, bronze_object, silver_object)
    third = load_gold_observations(connect_spark, silver_object, gold_object)
    assert third.inserted_rows == 0
    assert third.updated_rows >= 1
    assert third.deleted_rows == 0
    assert third.reconciliation_delta == 0

    after_previous = connect_spark.table(gold_object).where("company_id='M1' AND metric_id='revenue'").collect()[0]
    assert after_previous["current_value"] == 130.0
    assert after_previous["previous_value"] == 70.0
    assert after_previous["change_value"] == 60.0

    # Delete behavior: remove key from current valid Silver set by making latest row invalid.
    invalidate_delete_key = [
        {
            "observation_id": "m-delete",
            "company_id": "M2",
            "metric_id": "margin",
            "period_id": "BAD",
            "value": 11.0,
            "ingested_at": (base + timedelta(minutes=10)).isoformat(),
        }
    ]
    load_bronze_observations(connect_spark, invalidate_delete_key, bronze_object)
    load_silver_observations(connect_spark, bronze_object, silver_object)
    fourth = load_gold_observations(connect_spark, silver_object, gold_object)
    assert fourth.inserted_rows == 0
    assert fourth.updated_rows == 0
    assert fourth.deleted_rows == 1
    assert fourth.reconciliation_delta == 0
    assert fourth.gold_final_row_count == fourth.silver_distinct_company_metric_keys


def test_gold_rejects_view_source_for_delete_capable_sync(connect_spark) -> None:
    bronze_object, silver_object, gold_object = _objects(connect_spark, "s3_view")
    base = datetime.now(UTC)
    rows = [
        {
            "observation_id": "view-1",
            "company_id": "V1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 42.0,
            "ingested_at": base.isoformat(),
        },
        {
            "observation_id": "view-2",
            "company_id": "V1",
            "metric_id": "revenue",
            "period_id": "2025Q4",
            "value": 41.0,
            "ingested_at": (base - timedelta(days=90)).isoformat(),
        },
    ]

    load_bronze_observations(connect_spark, rows, bronze_object)
    load_silver_observations(connect_spark, bronze_object, silver_object)
    load_gold_observations(connect_spark, silver_object, gold_object)

    unsafe_view = f"tmp_vigie_gold_source_{uuid4().hex}"
    connect_spark.table(silver_object).where("company_id = 'V1'").createOrReplaceTempView(unsafe_view)
    try:
        with pytest.raises(ValueError, match="persisted full snapshot table"):
            load_gold_observations(connect_spark, unsafe_view, gold_object)
    finally:
        connect_spark.catalog.dropTempView(unsafe_view)
