from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from uuid import uuid4

import pytest

from vigie_databricks.finance_documents import create_financial_document
from vigie_databricks.finance_storage import (
    upsert_finance_run_audit,
    upsert_financial_documents,
)
from vigie_databricks.insurer_contract import load_insurer_contract


pytestmark = pytest.mark.databricks_connect
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def connect_spark():
    try:
        from databricks.connect import DatabricksSession
    except ImportError:
        pytest.skip("Databricks Connect is not installed in the current environment.")
    builder = DatabricksSession.builder
    profile = os.environ.get("DATABRICKS_CONNECT_PROFILE")
    cluster_id = os.environ.get("DATABRICKS_CLUSTER_ID")
    if profile:
        builder = builder.profile(profile)
    if cluster_id:
        builder = builder.clusterId(cluster_id)
    else:
        builder = builder.serverless(True)
    try:
        return builder.getOrCreate()
    except Exception as error:
        pytest.skip(f"Databricks Connect session unavailable: {error}")


def test_finance_documents_and_audit_are_idempotent_delta_upserts(connect_spark):
    context = connect_spark.sql(
        "SELECT current_catalog() AS catalog, current_schema() AS schema"
    ).collect()[0]
    suffix = uuid4().hex
    documents_object = (
        f"{context['catalog']}.{context['schema']}.vigie_finance_documents_{suffix}"
    )
    audit_object = f"{context['catalog']}.{context['schema']}.vigie_finance_audit_{suffix}"
    contract = load_insurer_contract(ROOT / "config")
    document = create_financial_document(
        contract,
        "MFC",
        "quarterly_report",
        "https://www.manulife.com/ca/en/about-us/investors/results-and-reports/q1.pdf",
        "fetched",
        content=b"fixture",
        content_type="application/pdf",
    )
    audit = {
        "run_id": "finance-connect-run",
        "observed_at": datetime.now(UTC),
        "source_mode": "candidate_fixture",
        "sources_succeeded": 0,
        "sources_failed": 0,
        "documents_discovered": 1,
        "documents_fetched": 1,
        "documents_unchanged": 0,
        "candidate_observations": 1,
        "ai_model_calls": 0,
        "retention_deleted_files": 0,
        "quality_status": "current",
    }

    upsert_financial_documents(connect_spark, documents_object, [document])
    upsert_financial_documents(connect_spark, documents_object, [document])
    upsert_finance_run_audit(connect_spark, audit_object, audit)
    upsert_finance_run_audit(connect_spark, audit_object, audit)

    assert connect_spark.table(documents_object).count() == 1
    assert connect_spark.table(audit_object).count() == 1
