from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
import os
import shutil
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations


pytestmark = pytest.mark.local_spark


def _spark_builder() -> SparkSession.Builder:
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.master("local[2]")
        .appName("vigie-databricks-slice1-tests")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
    )
    return builder


@pytest.fixture(scope="session")
def spark() -> Generator[SparkSession, None, None]:
    if shutil.which("java") is None and not os.environ.get("JAVA_HOME"):
        pytest.skip("Spark local tests require Java (JAVA_HOME or java on PATH).")

    try:
        from delta import configure_spark_with_delta_pip
    except Exception:
        pytest.skip("Local Spark tests require optional dependency delta-spark.")

    spark_session = configure_spark_with_delta_pip(_spark_builder()).getOrCreate()
    yield spark_session
    spark_session.stop()


def _sample_rows() -> list[dict]:
    now = datetime.now(UTC)
    return [
        {
            "observation_id": "obs-1",
            "company_id": "A",
            "metric_id": "revenue",
            "period_id": "2025Q4",
            "value": 120.0,
            "ingested_at": now.isoformat(),
        },
        {
            "observation_id": "obs-1",
            "company_id": "A",
            "metric_id": "revenue",
            "period_id": "2025Q4",
            "value": 121.0,
            "ingested_at": now.replace(microsecond=0).isoformat(),
        },
        {
            "observation_id": "obs-2",
            "company_id": "A",
            "metric_id": "margin",
            "period_id": "2025Q4",
            "value": 31.5,
            "ingested_at": now.isoformat(),
        },
    ]


def test_bronze_load_deduplicates_input_batch(spark: SparkSession) -> None:
    table_name = f"default.vigie_bronze_local_{uuid4().hex}"

    result = load_bronze_observations(spark=spark, rows=_sample_rows(), bronze_object=table_name)

    assert result.bronze_object == table_name
    assert result.input_rows == 3
    assert result.batch_rows_after_dedup == 2
    assert result.inserted_rows == 2
    assert result.updated_rows == 0
    assert result.final_row_count == 2


def test_bronze_rerun_is_idempotent(spark: SparkSession) -> None:
    table_name = f"default.vigie_bronze_idempotent_{uuid4().hex}"
    rows = _sample_rows()

    first_run = load_bronze_observations(spark=spark, rows=rows, bronze_object=table_name)
    second_run = load_bronze_observations(spark=spark, rows=rows, bronze_object=table_name)

    assert first_run.final_row_count == 2
    assert second_run.input_rows == 3
    assert second_run.batch_rows_after_dedup == 2
    assert second_run.inserted_rows == 0
    assert second_run.updated_rows == 0
    assert second_run.final_row_count == 2