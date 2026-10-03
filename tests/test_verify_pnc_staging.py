import json

import pytest

from scripts.verify_pnc_staging import (
    build_period_queries,
    build_readback_report,
    main,
)


def sample_readback_rows():
    audit_rows = [{
        "run_id": "12345", "status": "needs_review", "documents_acquired": 1,
        "candidate_count": 2, "ai_model_calls": 0, "errors_json": "[]",
    }]
    document_rows = [{
        "company_id": "IFC", "reporting_period": "2022-Q1",
        "content_hash": "a" * 64, "document_id": "doc-1",
        "acquisition_status": "fetched",
    }]
    candidate_rows = [{
        "company_id": "IFC", "period_id": "2022-Q1",
        "source_document_hash": "a" * 64, "candidate_id": "cand-1",
        "observation_id": "IFC-2022-Q1-net_income", "payload_json": "{}",
    }, {
        "company_id": "IFC", "period_id": "2022-Q1",
        "source_document_hash": "a" * 64, "candidate_id": "cand-2",
        "observation_id": "IFC-2022-Q1-net_income", "payload_json": "{}",
    }]
    return audit_rows, document_rows, candidate_rows


def candidate_with_unknown_hash():
    return {
        "company_id": "IFC", "period_id": "2022-Q1",
        "source_document_hash": "b" * 64, "candidate_id": "cand-bad",
        "observation_id": "IFC-2022-Q1-net_income", "payload_json": "{}",
    }


def test_build_period_queries_uses_only_requested_period():
    queries = build_period_queries("workspace.vigie", "2022-Q2", None)
    assert "2022-Q2" in queries["documents"]
    assert "2022-Q2" in queries["candidates"]


def test_build_period_queries_omits_audit_without_run_id():
    assert "audit" not in build_period_queries("workspace.vigie", "2022-Q2", None)


def test_build_period_queries_selects_exact_run_audit():
    queries = build_period_queries("workspace.vigie", "2022-Q2", "12345")
    assert "run_id = '12345'" in queries["audit"]


def test_period_queries_select_provenance_and_missing_source_fields():
    queries = build_period_queries("workspace.vigie", "2022-Q2", "12345")
    assert "source_url" in queries["documents"]
    assert "raw_content_path" in queries["documents"]
    assert "missing_sources_json" in queries["audit"]


def test_verification_inputs_reject_unsafe_values():
    with pytest.raises(ValueError):
        build_period_queries("workspace.vigie; DROP TABLE pnc_candidates", "2022-Q2", None)
    with pytest.raises(ValueError):
        build_period_queries("workspace.vigie", "2022-Q5", None)
    with pytest.raises(ValueError):
        build_period_queries("workspace.vigie", "2022-Q2", "12345'; --")


def test_readback_reports_hash_and_duplicate_revisions():
    audit_rows, document_rows, candidate_rows = sample_readback_rows()
    report = build_readback_report("2022-Q1", "12345", audit_rows, document_rows, candidate_rows)
    assert report["duplicate_observation_keys"] == ["IFC-2022-Q1-net_income"]
    assert report["hash_mismatches"] == []
    assert report["verification_status"] == "verified"


def test_readback_reports_missing_audit_with_staged_rows():
    _, document_rows, candidate_rows = sample_readback_rows()
    report = build_readback_report("2022-Q1", "12345", [], document_rows, candidate_rows)
    assert report["verification_status"] == "partial"
    assert report["documents"] == document_rows
    assert report["candidates"] == candidate_rows


def test_readback_marks_candidate_without_matching_document_hash():
    audit_rows, document_rows, _ = sample_readback_rows()
    report = build_readback_report("2022-Q1", "12345", audit_rows, document_rows,
                                   [candidate_with_unknown_hash()])
    assert report["hash_mismatches"]
    assert report["verification_status"] == "inconsistent"


def test_readback_hash_mismatch_overrides_missing_audit():
    _, document_rows, _ = sample_readback_rows()
    report = build_readback_report("2022-Q1", "12345", [], document_rows,
                                   [candidate_with_unknown_hash()])
    assert report["verification_status"] == "inconsistent"
    assert report["audit"] is None


def test_readback_hash_mismatch_overrides_duplicate_audit():
    audit_rows, document_rows, _ = sample_readback_rows()
    report = build_readback_report("2022-Q1", "12345", audit_rows * 2, document_rows,
                                   [candidate_with_unknown_hash()])
    assert report["verification_status"] == "inconsistent"
    assert report["audit"] is None


def test_readback_duplicate_audit_is_partial_with_null_audit():
    audit_rows, document_rows, candidate_rows = sample_readback_rows()
    report = build_readback_report("2022-Q1", "12345", audit_rows * 2,
                                   document_rows, candidate_rows)
    assert report["verification_status"] == "partial"
    assert report["audit"] is None


def test_readback_normalizes_audit_errors_to_strings():
    audit_rows, document_rows, candidate_rows = sample_readback_rows()
    audit_rows[0]["errors_json"] = '[{"code":"E1","detail":"bad"},"second"]'
    report = build_readback_report("2022-Q1", "12345", audit_rows,
                                   document_rows, candidate_rows)
    assert report["validation_errors"] == ['{"code":"E1","detail":"bad"}', "second"]
    assert all(isinstance(error, str) for error in report["validation_errors"])


def test_readback_accepts_empty_error_mapping():
    audit_rows, document_rows, candidate_rows = sample_readback_rows()
    audit_rows[0]["errors_json"] = "{}"
    report = build_readback_report("2022-Q1", "12345", audit_rows,
                                   document_rows, candidate_rows)
    assert report["validation_errors"] == []
    assert report["verification_status"] == "verified"


def test_readback_normalizes_nonempty_error_mapping_deterministically():
    audit_rows, document_rows, candidate_rows = sample_readback_rows()
    audit_rows[0]["errors_json"] = '{"ZZZ":"ValueError","AAA":"TimeoutError"}'
    report = build_readback_report("2022-Q1", "12345", audit_rows,
                                   document_rows, candidate_rows)
    assert report["validation_errors"] == ["AAA: TimeoutError", "ZZZ: ValueError"]
    assert report["verification_status"] == "inconsistent"


def test_readback_marks_non_review_audit_inconsistent():
    audit_rows, document_rows, candidate_rows = sample_readback_rows()
    audit_rows[0]["status"] = "extraction_incomplete"
    report = build_readback_report("2022-Q1", "12345", audit_rows, document_rows, candidate_rows)
    assert report["verification_status"] == "inconsistent"


def test_readback_baseline_has_no_run_audit():
    _, document_rows, candidate_rows = sample_readback_rows()
    report = build_readback_report("2022-Q1", None, [], document_rows, candidate_rows)
    assert report["verification_status"] == "baseline"
    assert report["audit"] is None


def test_cli_emits_baseline_and_post_run_json_without_writes(monkeypatch, capsys):
    import scripts.verify_pnc_staging as verifier

    class Result:
        def __init__(self, statement_id, rows):
            self.statement_id = statement_id
            self.status = type("Status", (), {"state": type("State", (), {"value": "SUCCEEDED"})()})()
            self.result = type("Data", (), {"data_array": rows})()

        def as_dict(self):
            return {"statement_id": self.statement_id}

    class Statements:
        def __init__(self):
            self.calls = []
            self.rows = [[], [["IFC", "2022-Q1", "a" * 64, "doc-1", "fetched",
                               "https://example.com/report", "/tmp/report.pdf"]],
                         [["IFC", "2022-Q1", "a" * 64, "cand-1", "IFC-2022-Q1-net_income", "{}"]]]

        def execute_statement(self, **kwargs):
            self.calls.append(kwargs)
            return Result(str(len(self.calls)), self.rows[len(self.calls) - 1])

        def get_statement(self, statement_id):
            raise AssertionError("successful statement should not be polled")

    statements = Statements()

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"profile": "jeplante"}
            self.statement_execution = statements

    monkeypatch.setattr(verifier, "WorkspaceClient", Client)
    monkeypatch.setattr(verifier.time, "sleep", lambda _: None)
    assert main(["--period", "2022-Q1"]) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["verification_status"] == "baseline"
    assert len(statements.calls) == 2
    assert all("SELECT" in call["statement"].upper() for call in statements.calls)

    statements.rows[2] = statements.rows[1]
    statements.rows.extend([statements.rows[1],
                            [["12345", "needs_review", 1, 1, 0, "[]", '["DOC-A"]']]])
    assert main(["--period", "2022-Q1", "--run-id", "12345"]) == 0
    post_run = json.loads(capsys.readouterr().out)
    assert post_run["audit"]["run_id"] == "12345"
    assert post_run["audit"]["missing_sources_json"] == '["DOC-A"]'
    assert post_run["documents"][0]["source_url"] == "https://example.com/report"
    assert post_run["documents"][0]["raw_content_path"] == "/tmp/report.pdf"
    assert post_run["verification_status"] == "verified"
    assert len(statements.calls) == 5
    assert "run_id = '12345'" in statements.calls[-1]["statement"]
    assert not any("INSERT" in call["statement"].upper() or "MERGE" in call["statement"].upper()
                   for call in statements.calls)
