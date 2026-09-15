"""Databricks task that turns quality failures into Job notifications."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json

from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

from vigie_databricks.operations_monitor import evaluate_operations, latest_completed_quarter


AUDIT_SCHEMA = "run_id string,observed_at timestamp,status string,alert_type string,severity string,entity string,message string"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-object", default="workspace.vigie.gold_observations")
    parser.add_argument("--finance-audit-object", default="workspace.vigie.finance_run_audit")
    parser.add_argument("--validated-object", default="workspace.vigie.finance_history_validated")
    parser.add_argument("--audit-object", default="workspace.vigie.operations_monitor_audit")
    parser.add_argument("--app-name", default="vigie-gold-viewer")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", choices=("true", "false"), default="true")
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    spark = SparkSession.builder.getOrCreate()
    observed_at = datetime.now(UTC)
    expected_period = latest_completed_quarter(observed_at)
    gold_rows = [row.asDict(recursive=True) for row in spark.table(args.gold_object).collect()]
    audit_rows = spark.sql(
        f"SELECT * FROM {args.finance_audit_object} ORDER BY observed_at DESC, run_id DESC LIMIT 1"
    ).collect()
    finance_audit = audit_rows[0].asDict(recursive=True) if audit_rows else None
    rejected_current = [row.asDict(recursive=True) for row in spark.sql(
        f"SELECT company_id,period_id,metric_id,validation_reason FROM {args.validated_object} "
        f"WHERE period_id='{expected_period}' AND validation_status='rejected'"
    ).collect()]
    app = WorkspaceClient().apps.get(args.app_name)
    app_state = str(getattr(getattr(app, "app_status", None), "state", "") or "").split(".")[-1]
    compute_state = str(getattr(getattr(app, "compute_status", None), "state", "") or "").split(".")[-1]
    alerts = evaluate_operations(
        gold_rows, finance_audit, rejected_current, expected_period=expected_period,
        app_state=app_state, compute_state=compute_state,
    )
    rows = [
        {
            "run_id": args.run_id, "observed_at": observed_at, "status": "alert",
            "alert_type": alert.alert_type, "severity": alert.severity,
            "entity": alert.entity, "message": alert.message,
        }
        for alert in alerts
    ] or [{
        "run_id": args.run_id, "observed_at": observed_at, "status": "healthy",
        "alert_type": "none", "severity": "info", "entity": "vigie",
        "message": f"Finance, {expected_period} et App validés.",
    }]
    if args.dry_run == "false":
        spark.createDataFrame(rows, AUDIT_SCHEMA).write.format("delta").mode("append").saveAsTable(args.audit_object)
    print(json.dumps({"expected_period": expected_period, "alerts": rows, "dry_run": args.dry_run == "true"}, default=str, sort_keys=True))
    if alerts:
        raise RuntimeError(f"{len(alerts)} operational alert(s) detected")


if __name__ == "__main__":
    main()
