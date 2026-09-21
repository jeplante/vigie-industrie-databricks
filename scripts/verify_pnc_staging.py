"""Read-only SQL verification of P&C revision keys and acquisition audits."""
import json
import time

from databricks.sdk import WorkspaceClient


SQL = """
SELECT 'candidates' AS dataset, company_id AS entity,
       COUNT(*) AS rows, COUNT(DISTINCT candidate_id) AS distinct_keys,
       COUNT(DISTINCT source_document_hash) AS document_revisions
FROM workspace.vigie.pnc_candidates GROUP BY company_id
UNION ALL
SELECT 'documents', company_id, COUNT(*), COUNT(DISTINCT document_id),
       COUNT(DISTINCT content_hash)
FROM workspace.vigie.pnc_financial_documents GROUP BY company_id
UNION ALL
SELECT 'audit', status, COUNT(*), COUNT(DISTINCT run_id), SUM(candidate_count)
FROM workspace.vigie.pnc_run_audit GROUP BY status
ORDER BY dataset, entity
"""


def main():
    client = WorkspaceClient(profile="jeplante")
    result = client.statement_execution.execute_statement(
        warehouse_id="9afffea8b155f79d", statement=SQL, wait_timeout="10s"
    )
    deadline = time.monotonic() + 180
    while result.status.state.value in {"PENDING", "RUNNING"} and time.monotonic() < deadline:
        time.sleep(5)
        result = client.statement_execution.get_statement(result.statement_id)
    print(json.dumps(result.as_dict(), default=str))
    if result.status.state.value != "SUCCEEDED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
