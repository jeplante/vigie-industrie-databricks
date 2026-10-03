"""Read-only, period-scoped SQL verification of P&C staging rows."""
import argparse
import json
import re
import time

from databricks.sdk import WorkspaceClient

from vigie_databricks.pnc_storage import pnc_tables


PROFILE = "jeplante"
WAREHOUSE_ID = "9afffea8b155f79d"
POLL_TIMEOUT_SECONDS = 180
WAIT_TIMEOUT = "10s"


def build_period_queries(namespace: str, period_id: str, run_id: str | None) -> dict[str, str]:
    tables = pnc_tables(namespace)
    if not isinstance(period_id, str) or not re.fullmatch(r"20\d{2}-Q[1-4]", period_id):
        raise ValueError("period_id must be a quarter such as 2022-Q1")
    if run_id is not None and (not isinstance(run_id, str)
                              or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id)):
        raise ValueError("run_id contains unsafe characters")

    queries = {
        "documents": (
            "SELECT company_id, reporting_period, content_hash, document_id, acquisition_status "
            f"FROM {tables['financial_documents']} WHERE reporting_period = '{period_id}'"
        ),
        "candidates": (
            "SELECT company_id, period_id, source_document_hash, candidate_id, observation_id, payload_json "
            f"FROM {tables['candidates']} WHERE period_id = '{period_id}'"
        ),
    }
    if run_id is not None:
        queries["audit"] = (
            "SELECT run_id, status, documents_acquired, candidate_count, ai_model_calls, errors_json "
            f"FROM {tables['run_audit']} WHERE run_id = '{run_id}'"
        )
    return queries


def _errors_for_audit(audit: dict) -> list:
    raw = audit.get("errors_json", "[]")
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return [f"audit errors_json is invalid: {raw}"]
    if not isinstance(parsed, list):
        return ["audit errors_json must contain a list"]
    return [item if isinstance(item, str) else json.dumps(
        item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ) for item in parsed]


def build_readback_report(period_id: str, run_id: str | None, audit_rows: list[dict],
                          document_rows: list[dict], candidate_rows: list[dict]) -> dict:
    documents = [row for row in document_rows if row.get("reporting_period") == period_id]
    candidates = [row for row in candidate_rows if row.get("period_id") == period_id]
    validation_errors = []
    observation_counts = {}
    for row in candidates:
        observation = row.get("observation_id")
        if not observation:
            validation_errors.append(
                f"candidate {row.get('candidate_id')!r} missing observation_id"
            )
        else:
            observation_counts[observation] = observation_counts.get(observation, 0) + 1
    duplicate_keys = sorted(key for key, count in observation_counts.items() if count > 1)

    hashes_by_company = {}
    for document in documents:
        company = document.get("company_id")
        content_hash = document.get("content_hash")
        if company and content_hash:
            hashes_by_company.setdefault(company, set()).add(content_hash)
    mismatches = []
    for candidate in candidates:
        company = candidate.get("company_id")
        source_hash = candidate.get("source_document_hash")
        if not source_hash or source_hash not in hashes_by_company.get(company, set()):
            mismatches.append({
                "company_id": company,
                "period_id": candidate.get("period_id"),
                "candidate_id": candidate.get("candidate_id"),
                "source_document_hash": source_hash,
            })

    selected_audit = None
    audit_errors = []
    if run_id is None:
        status = "baseline"
    else:
        matching_audits = [row for row in audit_rows if str(row.get("run_id")) == str(run_id)]
        if len(matching_audits) != 1:
            status = "partial"
            if not matching_audits:
                validation_errors.append(f"no audit row found for run_id {run_id}")
            else:
                validation_errors.append(f"multiple audit rows found for run_id {run_id}")
        else:
            selected_audit = matching_audits[0]
            audit_errors = _errors_for_audit(selected_audit)
            if audit_errors:
                validation_errors.extend(audit_errors)
            if selected_audit.get("status") != "needs_review" or audit_errors or mismatches:
                status = "inconsistent"
            else:
                status = "verified"

    if mismatches and run_id is not None:
        status = "inconsistent"
    return {
        "period_id": period_id,
        "run_id": run_id,
        "verification_status": status,
        "audit": selected_audit,
        "documents": documents,
        "candidates": candidates,
        "duplicate_observation_keys": duplicate_keys,
        "hash_mismatches": mismatches,
        "validation_errors": validation_errors,
    }


def _rows(result, names):
    data = getattr(getattr(result, "result", None), "data_array", None) or []
    schema = getattr(getattr(result, "manifest", None), "schema", None)
    columns = getattr(schema, "columns", None)
    if columns:
        names = [getattr(column, "name", column) for column in columns]
    return [dict(zip(names, row)) for row in data]


def _execute_query(client, statement):
    result = client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID, statement=statement, wait_timeout=WAIT_TIMEOUT
    )
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while result.status.state.value in {"PENDING", "RUNNING"} and time.monotonic() < deadline:
        time.sleep(5)
        result = client.statement_execution.get_statement(result.statement_id)
    if result.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"statement did not succeed: {result.status.state.value}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--namespace", default="workspace.vigie")
    args = parser.parse_args(argv)
    queries = build_period_queries(args.namespace, args.period, args.run_id)
    client = WorkspaceClient(profile=PROFILE)
    column_names = {
        "documents": ["company_id", "reporting_period", "content_hash", "document_id", "acquisition_status"],
        "candidates": ["company_id", "period_id", "source_document_hash", "candidate_id", "observation_id", "payload_json"],
        "audit": ["run_id", "status", "documents_acquired", "candidate_count", "ai_model_calls", "errors_json"],
    }
    results = {key: _rows(_execute_query(client, statement), column_names[key])
               for key, statement in queries.items()}
    report = build_readback_report(args.period, args.run_id, results.get("audit", []),
                                   results["documents"], results["candidates"])
    print(json.dumps(report, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
