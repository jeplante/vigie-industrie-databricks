"""Read staging through SQL and report the actual publication eligibility."""
import json
from pathlib import Path
import time
import yaml

from databricks.sdk import WorkspaceClient
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_review import review_pnc_candidates, attach_reviewed_evidence


def query(client, sql):
    response = client.statement_execution.execute_statement(
        warehouse_id="9afffea8b155f79d", statement=sql, wait_timeout="10s")
    deadline = time.monotonic() + 120
    while response.status.state.value in {"PENDING", "RUNNING"} and time.monotonic() < deadline:
        time.sleep(3)
        response = client.statement_execution.get_statement(response.statement_id)
    if response.status.state.value != "SUCCEEDED" or response.manifest.truncated:
        raise RuntimeError("Review query failed or was truncated")
    if response.manifest.total_chunk_count != 1:
        raise RuntimeError("Review requires pagination before processing")
    return [json.loads(row[0]) for row in response.result.data_array or []]


def main():
    client = WorkspaceClient(profile="jeplante")
    candidates = query(client, "SELECT payload_json FROM workspace.vigie.pnc_candidates")
    documents = query(client, "SELECT to_json(struct(*)) FROM workspace.vigie.pnc_financial_documents")
    contract = load_insurer_contract(Path(__file__).resolve().parents[1] / "config/pnc")
    reviews = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/pnc/reviewed_evidence.yaml").read_text())["reviews"]
    candidates = attach_reviewed_evidence(candidates, reviews)
    print(json.dumps(review_pnc_candidates(candidates, documents, contract), ensure_ascii=False))


if __name__ == "__main__":
    main()
