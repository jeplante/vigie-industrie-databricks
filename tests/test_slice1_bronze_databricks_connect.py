from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import os
from uuid import uuid4

import pytest

from vigie_databricks.bronze import load_bronze_observations


pytestmark = pytest.mark.databricks_connect


def _payload_hash_key(row: dict) -> str:
    parts = [row["company_id"], row["metric_id"], row["period_id"], str(row["value"])]
    return sha256("||".join(parts).encode("utf-8")).hexdigest()


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


def test_databricks_connect_bronze_idempotence(connect_spark) -> None:
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze_object = f"{context['catalog']}.{context['schema']}.vigie_bronze_connect_{uuid4().hex}"

    now = datetime.now(UTC).isoformat()
    rows = [
        {
            "observation_id": "conn-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 150.0,
            "ingested_at": now,
        },
        {
            "observation_id": "conn-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 150.0,
            "ingested_at": now,
        },
        {
            "observation_id": "conn-2",
            "company_id": "C1",
            "metric_id": "margin",
            "period_id": "2026Q2",
            "value": 22.4,
            "ingested_at": now,
        },
    ]

    first = load_bronze_observations(connect_spark, rows, bronze_object)
    second = load_bronze_observations(connect_spark, rows, bronze_object)

    final_df = connect_spark.table(bronze_object)
    final_row_count = final_df.count()
    final_distinct_count = final_df.select("observation_id").distinct().count()

    assert first.input_rows == 3
    assert first.batch_rows_after_dedup == 2
    assert first.inserted_rows == 2
    assert first.updated_rows == 0

    assert second.input_rows == 3
    assert second.batch_rows_after_dedup == 2
    assert second.inserted_rows == 0
    assert second.updated_rows == 0

    assert final_row_count == 2
    assert final_distinct_count == 2


def test_databricks_connect_dedup_is_deterministic_on_timestamp_tie(connect_spark) -> None:
    context = connect_spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    bronze_object = f"{context['catalog']}.{context['schema']}.vigie_bronze_tie_{uuid4().hex}"

    tied_timestamp = datetime(2026, 8, 8, 12, 0, tzinfo=UTC).isoformat()
    rows = [
        {
            "observation_id": "tie-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 100.0,
            "ingested_at": tied_timestamp,
        },
        {
            "observation_id": "tie-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 200.0,
            "ingested_at": tied_timestamp,
        },
    ]
    expected_winner = max(rows, key=_payload_hash_key)

    first = load_bronze_observations(connect_spark, rows, bronze_object)
    second = load_bronze_observations(connect_spark, rows, bronze_object)

    selected = connect_spark.table(bronze_object).select("value").collect()

    assert first.inserted_rows == 1
    assert first.updated_rows == 0
    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert [row["value"] for row in selected] == [expected_winner["value"]]