"""Promote reviewed historical quarterly candidates without advancing ambiguous data."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json

from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations
from vigie_databricks.finance_history import VALIDATED_STATUS, validate_historical_candidate
from vigie_databricks.gold import load_gold_observations
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
    parser.add_argument("--through-period", default="2025-Q4")
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


def main() -> None:
    args = _arguments()
    spark = SparkSession.builder.getOrCreate()
    candidates = [row.asDict(recursive=True) for row in spark.table(args.candidates_object).collect()]
    documents = [row.asDict(recursive=True) for row in spark.table(args.documents_object).collect()]
    documents_by_hash = {row["content_hash"]: row for row in documents if row.get("content_hash")}
    reviewed = []
    for candidate in candidates:
        status, reason = validate_historical_candidate(candidate, documents_by_hash.get(candidate.get("source_document_hash")))
        reviewed.append({
            **{key: candidate.get(key) for key in ("observation_id", "company_id", "period_id", "metric_id", "value", "unit", "source_url", "source_document_hash", "context")},
            "validation_status": status, "validation_reason": reason, "reviewed_at": datetime.now(UTC),
        })
    eligible = [row for row in reviewed if row["validation_status"] == VALIDATED_STATUS and row["period_id"] <= args.through_period]
    companies = {row["company_id"] for row in eligible}
    if companies != {"MFC", "SLF", "GWO", "IAG"}:
        raise ValueError("historical validation does not cover all four insurers")
    audit = {
        "run_id": args.run_id, "observed_at": datetime.now(UTC), "through_period": args.through_period,
        "reviewed_candidates": len(reviewed), "validated_quarterly": len(eligible),
        "rejected_candidates": len(reviewed) - sum(row["validation_status"] == VALIDATED_STATUS for row in reviewed),
        "dry_run": args.dry_run == "true",
    }
    if args.dry_run == "true":
        print(json.dumps(audit, default=str, sort_keys=True))
        return
    _upsert(spark, args.validated_object, reviewed, VALIDATED_SCHEMA, "observation_id")
    bronze_rows = [
        {key: row[key] for key in ("observation_id", "company_id", "metric_id", "period_id", "value")}
        for row in eligible
    ]
    bronze = load_bronze_observations(spark, bronze_rows, args.bronze_object)
    silver = load_silver_observations(spark, args.bronze_object, args.silver_object)
    gold = load_gold_observations(spark, args.silver_object, args.gold_object)
    if silver.reconciliation_delta != 0 or gold.reconciliation_delta != 0:
        raise ValueError("historical publication reconciliation failed")
    audit.update({"bronze": json.dumps(asdict(bronze)), "silver": json.dumps(asdict(silver)), "gold": json.dumps(asdict(gold))})
    spark.createDataFrame([audit]).write.format("delta").mode("append").saveAsTable(args.audit_object)
    print(json.dumps(audit, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
