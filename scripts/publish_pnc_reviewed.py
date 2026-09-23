"""Publish only explicitly reviewed P&C revisions through an atomic Delta MERGE."""
import argparse
import json
from pathlib import Path
import time
import yaml

from databricks.sdk import WorkspaceClient
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_review import attach_reviewed_evidence
from vigie_databricks.pnc_publication import publish_pnc_candidates
from review_pnc_staging import query

TABLE = "workspace.vigie.pnc_gold_observations"
SCHEMA = ("observation_id STRING,company_id STRING,metric_id STRING,period_id STRING,"
          "value DOUBLE,unit STRING,period_end STRING,calendar_basis STRING,disclosure_scope STRING,"
          "source_url STRING,source_document_hash STRING,validation_status STRING,evidence_json STRING")


def execute(client, sql):
    result = client.statement_execution.execute_statement(
        warehouse_id="9afffea8b155f79d", statement=sql, wait_timeout="10s")
    deadline = time.monotonic() + 180
    while result.status.state.value in {"PENDING", "RUNNING"} and time.monotonic() < deadline:
        time.sleep(3)
        result = client.statement_execution.get_statement(result.statement_id)
    if result.status.state.value != "SUCCEEDED":
        raise RuntimeError(str(result.status))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    client = WorkspaceClient(profile="jeplante")
    root = Path(__file__).resolve().parents[1]
    contract = load_insurer_contract(root / "config/pnc")
    reviews = yaml.safe_load((root / "config/pnc/reviewed_evidence.yaml").read_text())["reviews"]
    candidates = query(client, "SELECT payload_json FROM workspace.vigie.pnc_candidates")
    documents = query(client, "SELECT to_json(struct(*)) FROM workspace.vigie.pnc_financial_documents")
    reviewed = [row for row in attach_reviewed_evidence(candidates, reviews) if row.get("basis_evidence")]
    expected = sum(len(review["metrics"]) for review in reviews)
    if len(reviewed) != expected:
        raise ValueError("Not every recorded review matches exactly one candidate")
    result = publish_pnc_candidates(reviewed, documents, [], contract)
    if result.quality_status != "current":
        raise ValueError(result.rejection_reasons)
    rows = []
    for row in result.observations:
        evidence = row["basis_evidence"]
        output = {key: row[key] for key in ("observation_id", "company_id", "metric_id", "period_id",
                   "value", "unit", "source_url", "source_document_hash", "validation_status")}
        for key in ("period_end", "calendar_basis", "disclosure_scope"):
            if not evidence.get(key):
                raise ValueError(f"Missing reviewed {key}")
            output[key] = evidence[key]
        output["evidence_json"] = json.dumps(evidence, sort_keys=True)
        rows.append(output)
    if args.publish:
        execute(client, f"CREATE TABLE IF NOT EXISTS {TABLE} ({SCHEMA}) USING DELTA")
        payload = json.dumps(rows, allow_nan=False).replace("\\", "\\\\").replace("'", "''")
        source = f"SELECT item.* FROM (SELECT explode(from_json('{payload}', 'ARRAY<STRUCT<{SCHEMA}>>')) AS item)"
        execute(client, f"MERGE INTO {TABLE} t USING ({source}) s ON t.observation_id=s.observation_id "
                        "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
        actual = query(client, f"SELECT to_json(struct(*)) FROM {TABLE}")
        by_id = {row["observation_id"]: row for row in actual}
        if len(by_id) != len(actual) or any(by_id.get(row["observation_id"]) != row for row in rows):
            raise RuntimeError("Publication readback differs from reviewed rows")
    print(json.dumps({"published": args.publish, "reviewed_count": len(rows), "table": TABLE}))


if __name__ == "__main__":
    main()
