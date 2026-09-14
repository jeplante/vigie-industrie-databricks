"""Promote reviewed historical quarterly candidates without advancing ambiguous data."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations
from vigie_databricks.finance_history import VALIDATED_STATUS, anomalous_observations, incomplete_periods, select_preferred_documents, validate_historical_candidate
from vigie_databricks.gold import load_gold_observations
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.silver import load_silver_observations


VALIDATED_SCHEMA = (
    "observation_id string,company_id string,period_id string,metric_id string,value double,unit string,"
    "source_url string,source_document_hash string,context string,validation_status string,validation_reason string,"
    "reviewed_at timestamp"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates-object", default="workspace.vigie.finance_history_candidates")
    parser.add_argument("--documents-object", default="workspace.vigie.financial_documents")
    parser.add_argument("--validated-object", default="workspace.vigie.finance_history_validated")
    parser.add_argument("--bronze-object", default="workspace.vigie.bronze_observations")
    parser.add_argument("--silver-object", default="workspace.vigie.silver_observations")
    parser.add_argument("--gold-object", default="workspace.vigie.gold_observations")
    parser.add_argument("--audit-object", default="workspace.vigie.finance_history_publish_audit")
    parser.add_argument("--config-directory", required=True)
    parser.add_argument("--through-period")
    parser.add_argument("--required-period", default="2025-Q2")
    parser.add_argument("--dry-run", choices=("true", "false"), default="true")
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def _upsert(spark: SparkSession, object_name: str, rows: list[dict], schema: str, key: str) -> None:
    source = spark.createDataFrame(rows, schema=schema)
    if not spark.catalog.tableExists(object_name):
        source.write.format("delta").mode("overwrite").saveAsTable(object_name)
        return
    view = "vigie_history_validation_source"
    source.createOrReplaceTempView(view)
    try:
        spark.sql(f"MERGE INTO {object_name} t USING {view} s ON t.{key}=s.{key} WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
    finally:
        spark.catalog.dropTempView(view)


def _table_version(spark: SparkSession, object_name: str) -> int:
    return int(spark.sql(f"DESCRIBE HISTORY {object_name} LIMIT 1").collect()[0]["version"])


def _replace_historical_scope(
    spark: SparkSession,
    bronze_object: str,
    eligible: list[dict],
    expected_periods: set[tuple[str, str]],
) -> int:
    """Remove demo and quarantined history so Bronze represents the reviewed snapshot."""
    scope = spark.createDataFrame(sorted(expected_periods), "company_id string,period_id string")
    eligible_ids = spark.createDataFrame(
        [(row["observation_id"],) for row in eligible], "observation_id string"
    )
    scope_view = f"vigie_history_scope_{uuid4().hex}"
    eligible_view = f"vigie_history_eligible_{uuid4().hex}"
    scope.createOrReplaceTempView(scope_view)
    eligible_ids.createOrReplaceTempView(eligible_view)
    try:
        condition = (
            f"(EXISTS (SELECT 1 FROM {scope_view} s WHERE s.company_id=t.company_id AND s.period_id=t.period_id) "
            f"AND NOT EXISTS (SELECT 1 FROM {eligible_view} e WHERE e.observation_id=t.observation_id)) "
            "OR t.company_id NOT IN ('MFC','SLF','GWO','IAG')"
        )
        removed = spark.sql(f"SELECT COUNT(*) count FROM {bronze_object} t WHERE {condition}").collect()[0]["count"]
        spark.sql(f"DELETE FROM {bronze_object} AS t WHERE {condition}")
        return int(removed)
    finally:
        spark.catalog.dropTempView(scope_view)
        spark.catalog.dropTempView(eligible_view)


def main() -> None:
    args = _arguments()
    spark = SparkSession.builder.getOrCreate()
    contract = load_insurer_contract(Path(args.config_directory))
    candidates = [row.asDict(recursive=True) for row in spark.table(args.candidates_object).collect()]
    documents = [row.asDict(recursive=True) for row in spark.table(args.documents_object).collect()]
    documents_by_hash = {row["content_hash"]: row for row in documents if row.get("content_hash")}
    reviewed = []
    for candidate in candidates:
        status, reason = validate_historical_candidate(candidate, documents_by_hash.get(candidate.get("source_document_hash")), contract)
        reviewed.append({
            **{key: candidate.get(key) for key in ("observation_id", "company_id", "period_id", "metric_id", "value", "unit", "source_url", "source_document_hash", "context")},
            "validation_status": status, "validation_reason": reason, "reviewed_at": datetime.now(UTC),
        })
    through_period = args.through_period or max((row["period_id"] for row in reviewed), default="")
    expected_periods = set(select_preferred_documents(documents).keys())
    incomplete = incomplete_periods(reviewed, expected_periods)
    anomalies = anomalous_observations(reviewed)
    for row in reviewed:
        if row["observation_id"] in anomalies and row["validation_status"] == VALIDATED_STATUS:
            row["validation_status"] = "rejected"
            row["validation_reason"] = anomalies[row["observation_id"]]
    eligible = [
        row for row in reviewed
        if row["validation_status"] == VALIDATED_STATUS
        and row["period_id"] <= through_period
    ]
    companies = {row["company_id"] for row in eligible}
    if companies != {"MFC", "SLF", "GWO", "IAG"}:
        raise ValueError("historical validation does not cover all four insurers")
    required_companies = {row["company_id"] for row in eligible if row["period_id"] == args.required_period}
    required_incomplete = {company for company, period in incomplete if period == args.required_period}
    if required_companies != {"MFC", "SLF", "GWO", "IAG"} or required_incomplete:
        raise ValueError(f"required historical period is incomplete: {args.required_period}")
    audit = {
        "run_id": args.run_id, "observed_at": datetime.now(UTC), "through_period": through_period,
        "reviewed_candidates": len(reviewed), "validated_quarterly": len(eligible),
        "rejected_candidates": len(reviewed) - sum(row["validation_status"] == VALIDATED_STATUS for row in reviewed),
        "dry_run": args.dry_run == "true",
        "incomplete_periods": len(incomplete), "anomalous_observations": len(anomalies),
        "removed_observations": 0,
    }
    if args.dry_run == "true":
        print(json.dumps(audit, default=str, sort_keys=True))
        return
    _upsert(spark, args.validated_object, reviewed, VALIDATED_SCHEMA, "observation_id")
    bronze_rows = [
        {key: row[key] for key in ("observation_id", "company_id", "metric_id", "period_id", "value")}
        for row in eligible
    ]
    versions = {
        object_name: _table_version(spark, object_name)
        for object_name in (args.bronze_object, args.silver_object, args.gold_object)
    }
    try:
        audit["removed_observations"] = _replace_historical_scope(
            spark, args.bronze_object, bronze_rows, expected_periods
        )
        bronze = load_bronze_observations(spark, bronze_rows, args.bronze_object)
        silver = load_silver_observations(spark, args.bronze_object, args.silver_object)
        gold = load_gold_observations(spark, args.silver_object, args.gold_object)
        if silver.reconciliation_delta != 0 or gold.reconciliation_delta != 0:
            raise ValueError("historical publication reconciliation failed")
    except Exception:
        for object_name in (args.gold_object, args.silver_object, args.bronze_object):
            spark.sql(f"RESTORE TABLE {object_name} TO VERSION AS OF {versions[object_name]}")
        raise
    audit.update({"bronze": json.dumps(asdict(bronze)), "silver": json.dumps(asdict(silver)), "gold": json.dumps(asdict(gold))})
    if spark.catalog.tableExists(args.audit_object):
        columns = {field.name for field in spark.table(args.audit_object).schema.fields}
        additions = []
        if "incomplete_periods" not in columns:
            additions.append("incomplete_periods LONG")
        if "anomalous_observations" not in columns:
            additions.append("anomalous_observations LONG")
        if "removed_observations" not in columns:
            additions.append("removed_observations LONG")
        if additions:
            spark.sql(f"ALTER TABLE {args.audit_object} ADD COLUMNS ({', '.join(additions)})")
    spark.createDataFrame([audit]).write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(args.audit_object)
    print(json.dumps(audit, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
