from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations


pytestmark = pytest.mark.databricks_runtime


@pytest.fixture(scope="session")
def databricks_spark() -> SparkSession:
    try:
        from pyspark.sql import SparkSession
    except Exception:
        pytest.skip("Databricks runtime acceptance requires pyspark availability in runtime environment.")

    spark = SparkSession.getActiveSession()
    if spark is None:
        pytest.skip(
            "Databricks acceptance test must be executed from a Databricks runtime with an active SparkSession."
        )

    workspace_url = spark.conf.get("spark.databricks.workspaceUrl", None)
    if workspace_url is None:
        pytest.skip("Databricks acceptance test skipped: not running inside Databricks runtime.")

    return spark


def test_databricks_bronze_acceptance(databricks_spark: SparkSession) -> None:
    now = datetime.now(UTC).isoformat()
    rows = [
        {
            "observation_id": "acc-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 150.0,
            "ingested_at": now,
        },
        {
            "observation_id": "acc-1",
            "company_id": "C1",
            "metric_id": "revenue",
            "period_id": "2026Q2",
            "value": 150.0,
            "ingested_at": now,
        },
        {
            "observation_id": "acc-2",
            "company_id": "C1",
            "metric_id": "margin",
            "period_id": "2026Q2",
            "value": 22.4,
            "ingested_at": now,
        },
    ]

    bronze_object = f"default.vigie_bronze_acceptance_{uuid4().hex}"
    first = load_bronze_observations(databricks_spark, rows, bronze_object)
    second = load_bronze_observations(databricks_spark, rows, bronze_object)

    assert first.input_rows == 3
    assert first.batch_rows_after_dedup == 2
    assert first.final_row_count == 2

    assert second.batch_rows_after_dedup == 2
    assert second.inserted_rows == 0
    assert second.updated_rows == 0
    assert second.final_row_count == 2