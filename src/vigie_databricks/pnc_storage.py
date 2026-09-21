"""Isolated Delta staging for P&C acquisition and review candidates."""

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
import re


def pnc_tables(namespace):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", namespace):
        raise ValueError("namespace must be a catalog.schema identifier")
    return {key: f"{namespace}.pnc_{key}" for key in ("financial_documents", "candidates", "run_audit")}


def candidate_records(candidates):
    records = {}
    for candidate in candidates:
        payload = json.dumps(candidate, sort_keys=True, ensure_ascii=False, allow_nan=False)
        # Preserve extraction revisions without overwriting reviewed evidence.
        identifier = hashlib.sha256(payload.encode()).hexdigest()
        records[identifier] = {
            "candidate_id": identifier, "observation_id": candidate["observation_id"],
            "company_id": candidate["company_id"], "period_id": candidate["period_id"],
            "source_document_hash": candidate["source_document_hash"],
            "payload_json": payload,
        }
    return list(records.values())


def latest_document_index(documents):
    """Choose the latest acquired revision deterministically for HTTP caching."""
    index = {}
    for document in documents:
        if document.get("acquisition_status") not in {"fetched", "unchanged"}:
            continue
        if not document.get("raw_content_path") or not document.get("content_hash"):
            continue
        url = document["source_url"]
        rank = (str(document.get("fetched_at") or ""), document["content_hash"])
        previous = index.get(url)
        if previous is None or rank > (str(previous.get("fetched_at") or ""), previous["content_hash"]):
            index[url] = document
    return index


def load_pnc_document_index(spark, namespace):
    table = pnc_tables(namespace)["financial_documents"]
    if not spark.catalog.tableExists(table):
        return {}
    return latest_document_index(row.asDict(recursive=True) for row in spark.table(table).collect())


def persist_pnc_acquisition(spark, namespace, run_id, result, expected_companies):
    from vigie_databricks.finance_storage import _upsert_rows
    from vigie_databricks.finance_documents import FINANCIAL_DOCUMENT_SCHEMA

    tables = pnc_tables(namespace)
    if not run_id or not str(run_id).strip():
        raise ValueError("run_id is required")
    records = candidate_records(result.candidates)
    present = {row["company_id"] for row in result.candidates}
    missing = sorted(set(expected_companies) - present)
    status = "acquisition_failed" if result.errors else "extraction_incomplete" if missing else "needs_review"
    audit = {
        "run_id": str(run_id), "observed_at": datetime.now(UTC),
        "status": status, "documents_acquired": len(result.documents),
        "candidate_count": len(records), "ai_model_calls": 0,
        "missing_sources_json": json.dumps(missing),
        "errors_json": json.dumps(result.errors, sort_keys=True),
    }
    # Revision IDs retain the raw provenance used by older candidates.
    documents = []
    for document in result.documents:
        row = asdict(document)
        row["document_id"] = hashlib.sha256(
            f"{document.document_id}:{document.content_hash}".encode()
        ).hexdigest()
        documents.append(row)
    _upsert_rows(spark, tables["financial_documents"], documents, FINANCIAL_DOCUMENT_SCHEMA, "document_id")
    _upsert_rows(spark, tables["candidates"], records,
                 "candidate_id string,observation_id string,company_id string,period_id string,"
                 "source_document_hash string,payload_json string", "candidate_id")
    _upsert_rows(spark, tables["run_audit"], [audit],
                 "run_id string,observed_at timestamp,status string,documents_acquired long,"
                 "candidate_count long,ai_model_calls long,missing_sources_json string,errors_json string", "run_id")
    return audit
