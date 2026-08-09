from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest

from vigie_databricks.bronze import load_bronze_observations
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


def test_silver_snapshot_sync_and_idempotent_rerun(connect_spark) -> None:
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze_object = f"{context['catalog']}.{context['schema']}.vigie_bronze_s2_{uuid4().hex}"
    silver_object = f"{context['catalog']}.{context['schema']}.vigie_silver_s2_{uuid4().hex}"

    now = datetime.now(UTC)
    bronze_rows = [
        {
            "observation_id": "s2-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 100.0,
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "s2-2",
            "company_id": "C1",
            "metric_id": "margin",
            "period_id": "2026Q2",
            "value": 20.5,
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "s2-bad-period",
            "company_id": "C1",
            "metric_id": "cash",
            "period_id": "2026-T2",
            "value": 11.0,
            "ingested_at": now.isoformat(),
        },
    ]

    load_bronze_observations(connect_spark, bronze_rows, bronze_object)

    first = load_silver_observations(connect_spark, bronze_object, silver_object)
    second = load_silver_observations(connect_spark, bronze_object, silver_object)

    assert first.inserted_rows == 2
    assert first.updated_rows == 0
    assert first.silver_deleted_rows == 0
    assert first.bronze_rejected_rows_total == 1
    assert first.bronze_rejected_rows_by_reason == {"invalid_period_id": 1}
    assert sum(first.bronze_rejected_rows_by_reason.values()) == first.bronze_rejected_rows_total
    assert first.reconciliation_delta == 0
    assert first.silver_final_row_count == first.bronze_distinct_valid_observation_ids

    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.silver_deleted_rows == 0
    assert second.reconciliation_delta == 0
    assert second.silver_final_row_count == second.bronze_distinct_valid_observation_ids


def test_silver_deletes_row_when_previously_valid_becomes_invalid(connect_spark) -> None:
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze_object = f"{context['catalog']}.{context['schema']}.vigie_bronze_s2_delete_{uuid4().hex}"
    silver_object = f"{context['catalog']}.{context['schema']}.vigie_silver_s2_delete_{uuid4().hex}"

    now = datetime.now(UTC)
    initial_rows = [
        {
            "observation_id": "s2-keep",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 100.0,
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "s2-flip",
            "company_id": "C1",
            "metric_id": "margin",
            "period_id": "2026Q2",
            "value": 20.0,
            "ingested_at": now.isoformat(),
        },
    ]
    load_bronze_observations(connect_spark, initial_rows, bronze_object)
    first = load_silver_observations(connect_spark, bronze_object, silver_object)
    assert first.silver_final_row_count == 2

    invalidating_update = [
        {
            "observation_id": "s2-flip",
            "company_id": "C1",
            "metric_id": "margin",
            "period_id": "2026-T2",
            "value": 20.0,
            "ingested_at": (now + timedelta(minutes=1)).isoformat(),
        }
    ]
    load_bronze_observations(connect_spark, invalidating_update, bronze_object)

    second = load_silver_observations(connect_spark, bronze_object, silver_object)

    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.silver_deleted_rows == 1
    assert second.bronze_rejected_rows_total == 1
    assert second.bronze_rejected_rows_by_reason == {"invalid_period_id": 1}
    assert sum(second.bronze_rejected_rows_by_reason.values()) == second.bronze_rejected_rows_total
    assert second.reconciliation_delta == 0
    assert second.silver_final_row_count == second.bronze_distinct_valid_observation_ids
    assert second.silver_final_row_count == 1


def test_silver_rejects_nan_and_infinities_as_invalid_value(connect_spark) -> None:
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze_object = f"{context['catalog']}.{context['schema']}.vigie_bronze_s2_nonfinite_{uuid4().hex}"
    silver_object = f"{context['catalog']}.{context['schema']}.vigie_silver_s2_nonfinite_{uuid4().hex}"

    now = datetime.now(UTC)
    rows = [
        {
            "observation_id": "finite-ok",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 10.0,
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "nan-row",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": float("nan"),
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "posinf-row",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": float("inf"),
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "neginf-row",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": float("-inf"),
            "ingested_at": now.isoformat(),
        },
    ]

    load_bronze_observations(connect_spark, rows, bronze_object)
    result = load_silver_observations(connect_spark, bronze_object, silver_object)

    assert result.bronze_rejected_rows_total == 3
    assert result.bronze_rejected_rows_by_reason == {"invalid_value": 3}
    assert sum(result.bronze_rejected_rows_by_reason.values()) == result.bronze_rejected_rows_total
    assert result.silver_final_row_count == 1
    assert result.bronze_distinct_valid_observation_ids == 1
    assert result.reconciliation_delta == 0
