import pytest

from vigie_databricks.pnc_storage import candidate_records, pnc_tables
from vigie_databricks.pnc_storage import latest_document_index
from vigie_databricks.pnc_storage import persist_pnc_acquisition
from vigie_databricks.pnc_live import PncAcquisitionResult


def test_table_names_are_isolated_and_reject_sql_fragments():
    assert pnc_tables("workspace.vigie")["candidates"] == "workspace.vigie.pnc_candidates"
    for name in ("workspace", "workspace.vigie; DROP TABLE x", "a.b.c", "a.`b`"):
        with pytest.raises(ValueError):
            pnc_tables(name)


def test_cache_chooses_latest_usable_revision_independent_of_row_order():
    old = dict(source_url="https://www.td.com/report.pdf", content_hash="a" * 64,
               raw_content_path="/Volumes/raw/old.pdf", acquisition_status="fetched", fetched_at="2026-09-20")
    recent = {**old, "content_hash": "b" * 64, "fetched_at": "2026-09-21"}
    failed = {**recent, "fetched_at": "2026-09-22", "acquisition_status": "failed"}
    expired = {**recent, "fetched_at": "2026-09-23", "raw_content_path": None}
    assert latest_document_index([recent, old, failed, expired]) == {old["source_url"]: recent}
    assert latest_document_index([expired, failed, old, recent]) == {old["source_url"]: recent}


def test_candidate_identity_is_idempotent_and_retains_extraction_revisions():
    candidate = dict(observation_id="TD-2026-Q2-net_income", company_id="TD", period_id="2026-Q2",
                     source_document_hash="a" * 64, value=.279)
    first = candidate_records([candidate, candidate])
    assert len(first) == 1
    assert first == candidate_records([dict(reversed(list(candidate.items())))])
    revised = candidate_records([candidate, {**candidate, "value": .280}])
    assert len(revised) == 2
    assert revised[0]["candidate_id"] != revised[1]["candidate_id"]


def test_staging_audits_incomplete_sources_without_writing_gold(monkeypatch):
    from vigie_databricks import finance_storage
    writes = []
    monkeypatch.setattr(finance_storage, "_upsert_rows", lambda *args: writes.append(args))
    candidate = dict(observation_id="TD-2026-Q2-net_income", company_id="TD", period_id="2026-Q2",
                     source_document_hash="a" * 64, value=.279)
    result = PncAcquisitionResult((), (candidate,), {"AV": "TimeoutError"})
    audit = persist_pnc_acquisition(object(), "workspace.vigie", "test-run", result,
                                    ("TD", "AV", "IFC", "DFY"))
    assert audit["status"] == "acquisition_failed"
    assert audit["candidate_count"] == 1
    assert audit["ai_model_calls"] == 0
    assert [args[1] for args in writes] == [
        "workspace.vigie.pnc_financial_documents", "workspace.vigie.pnc_candidates",
        "workspace.vigie.pnc_run_audit",
    ]
