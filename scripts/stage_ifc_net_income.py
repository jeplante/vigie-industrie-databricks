"""Stage the reviewed IFC Q2 net-income extraction from its stored raw report."""

import argparse
import hashlib
import json
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_extraction import extract_pnc_metrics
from vigie_databricks.pnc_history import PNC_REVIEW_STATUS
from vigie_databricks.pnc_storage import candidate_records
from review_pnc_staging import query
from publish_pnc_reviewed import execute

TABLE = "workspace.vigie.pnc_candidates"
RAW_ROOT = "/Volumes/workspace/vigie/pnc_finance_raw/"


def build_candidate(client, root):
    contract = load_insurer_contract(root / "config/pnc")
    reviews = yaml.safe_load((root / "config/pnc/reviewed_evidence.yaml").read_text(encoding="utf-8"))["reviews"]
    review = next(item for item in reviews if item["company_id"] == "IFC" and item["period_id"] == "2026-Q2")
    documents = query(client, "SELECT to_json(struct(*)) FROM workspace.vigie.pnc_financial_documents WHERE company_id = 'IFC'")
    matches = [item for item in documents if item["content_hash"] == review["source_document_hash"]]
    if len(matches) != 1:
        raise ValueError("Expected one exact IFC report revision")
    document = matches[0]
    if document["reporting_period"] != review["period_id"] or not document["raw_content_path"].startswith(RAW_ROOT):
        raise ValueError("Unexpected IFC period or raw path")
    content = client.files.download(document["raw_content_path"]).contents.read()
    if hashlib.sha256(content).hexdigest() != document["content_hash"]:
        raise ValueError("Stored IFC report hash mismatch")
    metrics = [item for item in extract_pnc_metrics("IFC", content.decode("utf-8"), contract)
               if item.metric_id == "net_income"]
    if len(metrics) != 1 or metrics[0].value != 0.720 or metrics[0].unit != "CAD_BILLION":
        raise ValueError("IFC net-income extraction differs from report review")
    metric = metrics[0]
    return {
        "observation_id": "IFC-2026-Q2-net_income",
        "company_id": "IFC", "period_id": "2026-Q2", "metric_id": metric.metric_id,
        "value": metric.value, "unit": metric.unit, "source_url": document["source_url"],
        "source_document_hash": document["content_hash"], "context": metric.context,
        "quality_status": "candidate", "validation_status": PNC_REVIEW_STATUS,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    client = WorkspaceClient(profile="jeplante")
    candidate = build_candidate(client, Path(__file__).resolve().parents[1])
    count = query(client, f"SELECT to_json(named_struct('n', count(*))) FROM {TABLE} "
                          "WHERE observation_id = 'IFC-2026-Q2-net_income'")[0]["n"]
    existing = (query(client, f"SELECT payload_json FROM {TABLE} "
                             "WHERE observation_id = 'IFC-2026-Q2-net_income'") if count else [])
    if any(item["value"] != candidate["value"] or item["unit"] != candidate["unit"]
           for item in existing):
        raise ValueError("Conflicting IFC net-income candidate")
    if args.persist:
        record = candidate_records([candidate])[0]
        payload = json.dumps([record], ensure_ascii=False, allow_nan=False).replace("\\", "\\\\").replace("'", "''")
        schema = ("candidate_id STRING,observation_id STRING,company_id STRING,period_id STRING,"
                  "source_document_hash STRING,payload_json STRING")
        source = f"SELECT item.* FROM (SELECT explode(from_json('{payload}', 'ARRAY<STRUCT<{schema}>>')) AS item)"
        execute(client, f"MERGE INTO {TABLE} t USING ({source}) s ON t.candidate_id=s.candidate_id "
                        "WHEN NOT MATCHED THEN INSERT *")
        actual = query(client, f"SELECT payload_json FROM {TABLE} WHERE candidate_id = '{record['candidate_id']}'")
        if actual != [candidate]:
            raise RuntimeError("IFC candidate readback differs from extraction")
    print(json.dumps({"persisted": args.persist, "candidate": candidate}, ensure_ascii=False))


if __name__ == "__main__":
    main()
