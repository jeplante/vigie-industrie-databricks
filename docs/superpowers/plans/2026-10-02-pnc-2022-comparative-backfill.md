# P&C 2022 Comparative Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stage the eligible IFC and Definity 2022 quarterly comparative candidates with exact acquired source hashes, verify all four periods, and leave the evidence package pending human review.

**Architecture:** Use current `origin/main` in an isolated worktree. Complete the missing Q4 end-to-end fixture coverage and add a read-only period verifier with pre-run and run-specific audit modes. Validate locally, submit one unscheduled acquisition per quarter in sequence, verify persisted staging state, update source-review documentation, then open and merge a CI-passing PR.

**Tech Stack:** Python 3.12, `uv`, pytest, PyYAML, Databricks SDK, Databricks Jobs and SQL Statement APIs.

**Spec:** [2026-10-02-pnc-2022-comparative-backfill-design.md](../specs/2026-10-02-pnc-2022-comparative-backfill-design.md)

## Global Constraints

- Start from current `origin/main` in an isolated worktree; leave the original dirty checkout untouched and port only missing work.
- Preserve the Python `>=3.12,<3.13` requirement and run the documented Python 3.12 local pytest gate.
- P&C remains manual, unscheduled, and separate from Life Finance.
- Remote writes are limited to the submitting user's versioned workspace upload folder, raw source files in the P&C Volume, and the P&C financial documents, candidates, and run-audit staging tables.
- Do not update reviewed evidence, publish Gold, modify persistent Jobs or schedules, or commit report bytes or secrets.
- Do not infer Aviva or TD values, and do not claim cross-table atomicity.
- Treat sequential staging writes as potentially partial; inspect state before retrying a failed run.
- Stop for human review after the staged values and exact hashes are documented.

## Review Focus

1. **Wrong comparative column or cumulative value:** Q2/Q3 reports include H1/YTD columns. `test_ifc_q1_to_q3_comparative_reads_restated_2022_values` and `test_definity_q1_to_q3_comparative_reads_restated_2022_values` already cover these; extend `test_2022_q4_acquisition_uses_comparative_not_current_column` to assert the full Q4 set.
2. **Unavailable or expected-no-candidate issuer produces a value:** retain the all-quarter manifest check and `test_td_gap_requires_acquired_report`; assert the Q4 end-to-end result has no TD or Aviva candidates.
3. **A pre-run check accidentally selects an audit or candidate for another period:** `test_build_period_queries_uses_only_requested_period` and `test_build_period_queries_omits_audit_without_run_id` pin the baseline mode.
4. **Unsafe SQL input or misleading run attribution:** `test_verification_inputs_reject_unsafe_values`, `test_build_period_queries_selects_exact_run_audit`, and `test_readback_reports_hash_and_duplicate_revisions` cover validation and the schema's lack of candidate `run_id`.
5. **Partial upsert mistaken for a completed run:** `test_readback_reports_missing_audit_with_staged_rows` verifies the incomplete state remains visible; remote steps require manual inspection before retry.

---

### Task 1: Complete the Q4 End-to-End Comparative Fixture

**Files:**
- Modify: `tests/test_pnc_2022_acquisition.py`

**Interfaces:**
- Consumes: `acquire_pnc_documents`, the current Q4 manifest, and the existing IFC/Definity extractors.
- Produces: an end-to-end Q4 fixture that asserts all nine eligible candidates and the zero-candidate issuer gaps.

- [ ] **Step 1: Confirm the isolated baseline**

Confirm the worktree is clean and `origin/main` is an ancestor of the current
branch. Run the documented local gate before changing code.

Run: `uv run --python 3.12 pytest -m "not databricks_connect and not databricks_runtime" -q`

Expected: PASS with any environment-dependent skips reported. Do not run
mutating commands from the original dirty checkout.

- [ ] **Step 2: Extend the assertion before extending the fixture**

In `test_2022_q4_acquisition_uses_comparative_not_current_column`, change the expected result to the full nine-key set:

```python
{
    ("IFC", "combined_ratio"): 93.2,
    ("IFC", "operating_income"): 0.508,
    ("IFC", "net_income"): 0.353,
    ("DFY", "insurance_revenue"): 0.9117,
    ("DFY", "claims_ratio"): 59.5,
    ("DFY", "expense_ratio"): 32.7,
    ("DFY", "combined_ratio"): 92.2,
    ("DFY", "operating_income"): 0.0766,
    ("DFY", "net_income"): 0.185,
}
```

Also assert `len(result.candidates) == 9` and no candidate has company ID `AV` or `TD`.

- [ ] **Step 3: Run the focused test and confirm the incomplete fixture fails**

Run: `uv run --python 3.12 pytest tests/test_pnc_2022_acquisition.py::test_2022_q4_acquisition_uses_comparative_not_current_column -q`

Expected: FAIL because the Q4 fixture currently includes only Definity revenue and net income.

- [ ] **Step 4: Add the official Q4 comparative rows to the fixture**

Add the Claims ratio (59.5%), Expense ratio (32.7%), Combined ratio (92.2%), and Operating net income (CAD 76.6m) comparative rows to the Definity report fixture. Preserve the Q4 2023 and Q4 2022 (Restated) columns so the test proves the extractor selects Q4 2022. Keep source values consistent with `docs/PNC_SOURCE_REVIEW.md`.

- [ ] **Step 5: Run the focused test and confirm it passes**

Run: `uv run --python 3.12 pytest tests/test_pnc_2022_acquisition.py::test_2022_q4_acquisition_uses_comparative_not_current_column -q`

Expected: PASS with exactly nine candidates and the exact metric/value set above.

If the completed official-source fixture still does not produce that set, use
`superpowers:systematic-debugging` on the existing `extract_pnc_metrics`
path and keep the failing assertion intact. Make only a source-format parsing
change needed for the restated Q4 rows. Stop for design review if producing the
expected set would require changing the eligible KPI or accounting basis.

- [ ] **Step 6: Commit the fixture coverage**

```bash
git add tests/test_pnc_2022_acquisition.py
git commit -m "test: cover all Q4 2022 P&C comparative candidates"
```

### Task 2: Add Test-First Period-Scoped Readback

**Files:**
- Create: `tests/test_verify_pnc_staging.py`
- Modify: `scripts/verify_pnc_staging.py`

**Interfaces:**
- Produces `build_period_queries(namespace: str, period_id: str, run_id: str | None) -> dict[str, str]`.
- Produces `build_readback_report(period_id: str, run_id: str | None, audit_rows: list[dict], document_rows: list[dict], candidate_rows: list[dict]) -> dict`.
- `run_id=None` means pre-run baseline and omits the audit query. A supplied run ID selects exactly that audit row.
- The query dictionary uses `documents` and `candidates` keys and includes `audit` only when a run ID is supplied.
- The report includes `period_id`, `run_id`, `verification_status` (`baseline`, `verified`, `partial`, or `inconsistent`), `audit` (or null), `documents`, `candidates`, `duplicate_observation_keys`, `hash_mismatches`, and `validation_errors`. A missing or duplicate run-audit row is `partial`; a candidate/document hash mismatch, failed audit, or nonempty audit error list is `inconsistent`; one `needs_review` audit with no errors and no hash mismatch is `verified`. It must not claim candidate-to-run linkage.

- [ ] **Step 1: Write unit tests for period and run query construction**

Add:

```python
def test_build_period_queries_uses_only_requested_period():
    queries = build_period_queries("workspace.vigie", "2022-Q2", None)
    assert "2022-Q2" in queries["documents"]
    assert "2022-Q2" in queries["candidates"]

def test_build_period_queries_omits_audit_without_run_id():
    assert "audit" not in build_period_queries("workspace.vigie", "2022-Q2", None)

def test_build_period_queries_selects_exact_run_audit():
    queries = build_period_queries("workspace.vigie", "2022-Q2", "12345")
    assert "run_id = '12345'" in queries["audit"]

def test_verification_inputs_reject_unsafe_values():
    with pytest.raises(ValueError):
        build_period_queries("workspace.vigie; DROP TABLE pnc_candidates", "2022-Q2", None)
    with pytest.raises(ValueError):
        build_period_queries("workspace.vigie", "2022-Q5", None)
    with pytest.raises(ValueError):
        build_period_queries("workspace.vigie", "2022-Q2", "12345'; --")
```

Assert document and candidate SQL use the requested quarter, baseline mode has no run-audit query, and post-run mode filters by the exact run ID. Cover invalid period, run ID, and catalog/schema values. Use the existing `pnc_tables` namespace validation.

- [ ] **Step 2: Run the new tests and confirm they fail**

Run: `uv run --python 3.12 pytest tests/test_verify_pnc_staging.py -q`

Expected: FAIL because the query and report helpers do not exist.

- [ ] **Step 3: Write readback report tests**

Add:

```python
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
    mismatched_candidates = [candidate_with_unknown_hash()]
    report = build_readback_report("2022-Q1", "12345", audit_rows, document_rows, mismatched_candidates)
    assert report["hash_mismatches"]
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
```

`sample_readback_rows()` returns an audit with run ID `12345`, status
`needs_review`, one acquired document, two candidates, zero AI calls, and
empty errors; an IFC Q1 document with hash `a` repeated 64 times; and two IFC
Q1 net-income candidate revisions with that same hash and observation ID
`IFC-2022-Q1-net_income`. `candidate_with_unknown_hash()` returns a Q1
candidate for the same issuer with hash `b` repeated 64 times and no matching
document row.

Use representative document and candidate dictionaries. Assert candidate hashes are matched against documents for the same issuer and period, old revisions and duplicate observation keys remain visible, and rows without an audit are reported as partial rather than silently treated as complete.

- [ ] **Step 4: Run report tests and confirm they fail**

Run: `uv run --python 3.12 pytest tests/test_verify_pnc_staging.py -q`

Expected: FAIL because the readback report function does not exist.

- [ ] **Step 5: Implement the validated period query builder**

Implement `build_period_queries` in `scripts/verify_pnc_staging.py`. Validate periods against `20\d{2}-Q[1-4]`; validate run IDs against a bounded safe-character pattern; validate namespaces through `pnc_tables`. Query documents by `reporting_period` and candidates by `period_id`; add an audit query only when a run ID is supplied. Keep all statements read-only.

- [ ] **Step 6: Re-run the query-construction tests**

Run: `uv run --python 3.12 pytest tests/test_verify_pnc_staging.py -q -k "build_period_queries or verification_inputs"`

Expected: query-construction and input-validation tests PASS; report tests remain unimplemented for the next step.

- [ ] **Step 7: Implement readback aggregation and consistency reporting**

Implement `build_readback_report` with the output contract above. Return period-scoped documents and candidates, duplicate observation keys, candidate/document hash mismatches, and validation errors. A baseline has `verification_status="baseline"`; a post-run result is `verified` only with one `needs_review` audit, no audit errors, and no hash mismatch. Missing/duplicate audits are `partial`; failed/incomplete audits and hash mismatches are `inconsistent`.

- [ ] **Step 8: Run the report tests and confirm they pass**

Run: `uv run --python 3.12 pytest tests/test_verify_pnc_staging.py -q -k "readback"`

Expected: report tests PASS for duplicate revisions, missing audit, baseline, source-hash mismatch, and non-review audit cases.

- [ ] **Step 9: Wire the helpers to the existing CLI**

Add `--period` (required), `--run-id` (optional), and `--namespace` (default `workspace.vigie`). Preserve the current profile, warehouse, polling timeout, and read-only behavior. Emit the report as JSON. A baseline invocation must work without a run ID; a post-run invocation must include the exact audit record.

- [ ] **Step 10: Test CLI wiring with a mocked WorkspaceClient**

Add a test that supplies three fake statement results and asserts the CLI emits baseline/post-run JSON without making any write call. Run: `uv run --python 3.12 pytest tests/test_verify_pnc_staging.py -q`.

- [ ] **Step 11: Commit verifier and tests**

```bash
git add scripts/verify_pnc_staging.py tests/test_verify_pnc_staging.py
git commit -m "feat: verify P&C staging by period and run"
```

**Parallel boundary:** Tasks 1 and 2 are independent and edit disjoint files.
Assign Task 1 to one fresh `gpt-6-luna` agent at medium reasoning effort and
Task 2 to a second fresh `gpt-6-luna` agent at medium reasoning effort. Neither
agent stages or commits files; the integrating agent reviews both diffs,
verifies the tests, and commits each task sequentially. All package/build,
remote staging, and documentation tasks wait until both tasks are integrated.

### Task 3: Validate All Quarter Manifests and Build the Wheel

**Files:**
- Read: `config/pnc/history/2022-Q1.yaml` through `config/pnc/history/2022-Q4.yaml`
- Read: `scripts/submit_pnc_history.py`
- Build: `dist/vigie_databricks_foundation-<project-version>-py3-none-any.whl`

**Interfaces:**
- Consumes: the manifest contract and `checked_manifest(path)`.
- Produces: a built wheel and validation-only summaries for all four periods.

- [ ] **Step 1: Run all-quarter focused validation**

Run: `uv run --python 3.12 pytest tests/test_pnc_2022_acquisition.py tests/test_pnc_history_submit.py tests/test_verify_pnc_staging.py -q`

Expected: PASS, including `checked_manifest` validation of all four 2022 manifests and exact comparative fixture coverage.

- [ ] **Step 2: Build the wheel from the current worktree**

Run: `uv build --wheel`

Expected: one wheel whose version matches `pyproject.toml`; do not upload it yet.

- [ ] **Step 3: Run validation-only submit summaries for every quarter**

Run these commands without `--submit`:

```powershell
uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q1.yaml --run-token preflight-q1
uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q2.yaml --run-token preflight-q2
uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q3.yaml --run-token preflight-q3
uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q4.yaml --run-token preflight-q4
```

Expected: each prints its matching `period_id`, current package version, and `submitted: false`; no Workspace API call or live write occurs.

- [ ] **Step 4: Run the documented local pytest gate**

Run: `uv run --python 3.12 pytest -m "not databricks_connect and not databricks_runtime" -q`

Expected: PASS; report the exact pass/skip counts. Run `git diff --check` and review the file list before any remote operation.

### Task 4: Preflight and Stage One Quarter at a Time

**Files:**
- Use: `scripts/submit_pnc_history.py`
- Use: `scripts/verify_pnc_staging.py`
- Use: `databricks_pnc_acquire_job.template.json`
- Remote targets: the submitting user's versioned workspace folder, configured P&C Volume, and `workspace.vigie` P&C staging tables

**Interfaces:**
- Consumes: Task 3 wheel, four validated manifests, workspace profile `jeplante`, and user-approved staging scope.
- Produces: four one-time run IDs, run audits, acquired document revisions, and period candidate revisions for human review.

Save each verifier's JSON output outside the repository under
`$env:TEMP\pnc-2022-staging-readback\`; compare each post-run result with its
period's pre-run output. Do not store source report bytes or credentials there.

- [ ] **Step 1: Preflight identity and write targets**

Using `WorkspaceClient(profile="jeplante")`, confirm the authenticated username with `current_user.me()`. Read the contract and job template to confirm the configured Volume (`/Volumes/workspace/vigie/pnc_finance_raw`), `workspace.vigie` schema, user-scoped artifact path, 600-second timeout, zero retries, and one-time Jobs API submission. Through the existing SQL Warehouse, run read-only `SHOW GRANTS ON VOLUME workspace.vigie.pnc_finance_raw`, `SHOW GRANTS ON SCHEMA workspace.vigie`, and `SHOW GRANTS ON TABLE` for `workspace.vigie.pnc_financial_documents`, `workspace.vigie.pnc_candidates`, and `workspace.vigie.pnc_run_audit`; confirm the identity has the required write privileges. Do not upload files or submit if identity, target namespace, or access is uncertain; report the specific blocker.

- [ ] **Step 2: Record Q1 pre-run staging state**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q1 --namespace workspace.vigie`

Expected: read-only period baseline, no run audit selected.

- [ ] **Step 3: Submit the Q1 one-time run**

Run: `uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q1.yaml --profile jeplante --run-token pnc2022q1-attempt01 --submit`

Capture the returned run ID. Poll that ID with `WorkspaceClient(profile="jeplante").jobs.get_run(run_id=<id>)` until terminal; expect `TERMINATED / SUCCESS`. Do not create a persistent Job or schedule.

- [ ] **Step 4: Verify Q1 staging before continuing**

Run the verifier with `--period 2022-Q1 --run-id <returned-run-id> --namespace workspace.vigie`. Confirm the exact `needs_review` audit with three acquired documents, nine candidates, and zero AI calls; verify IFC's three and Definity's six expected metrics, no TD/Aviva candidates, target period, matching document hashes, and P&C Volume paths. Compare the post-run state with the Q1 baseline.

- [ ] **Step 5: Record Q2 pre-run staging state**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q2 --namespace workspace.vigie`

Expected: read-only Q2 baseline, no run audit selected.

- [ ] **Step 6: Submit the Q2 one-time run**

Run: `uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q2.yaml --profile jeplante --run-token pnc2022q2-attempt01 --submit`

Capture the returned run ID and monitor it with `jobs.get_run(run_id=<id>)` to `TERMINATED / SUCCESS`.

- [ ] **Step 7: Verify Q2 staging before continuing**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q2 --run-id <returned-run-id> --namespace workspace.vigie`

Expected: the Q2 audit and period rows meet all audit, metric, hash, gap, and Volume-path checks listed in Task 4, Step 4.

- [ ] **Step 8: Record Q3 pre-run staging state**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q3 --namespace workspace.vigie`

Expected: read-only Q3 baseline, no run audit selected.

- [ ] **Step 9: Submit the Q3 one-time run**

Run: `uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q3.yaml --profile jeplante --run-token pnc2022q3-attempt01 --submit`

Capture the returned run ID and monitor it with `jobs.get_run(run_id=<id>)` to `TERMINATED / SUCCESS`.

- [ ] **Step 10: Verify Q3 staging before continuing**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q3 --run-id <returned-run-id> --namespace workspace.vigie`

Expected: the Q3 audit and period rows meet all audit, metric, hash, gap, and Volume-path checks listed in Task 4, Step 4.

- [ ] **Step 11: Record Q4 pre-run staging state**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q4 --namespace workspace.vigie`

Expected: read-only Q4 baseline, no run audit selected.

- [ ] **Step 12: Submit the Q4 one-time run**

Run: `uv run --python 3.12 python scripts/submit_pnc_history.py --manifest config/pnc/history/2022-Q4.yaml --profile jeplante --run-token pnc2022q4-attempt01 --submit`

Capture the returned run ID and monitor it with `jobs.get_run(run_id=<id>)` to `TERMINATED / SUCCESS`.

- [ ] **Step 13: Verify Q4 staging**

Run: `uv run --python 3.12 python scripts/verify_pnc_staging.py --period 2022-Q4 --run-id <returned-run-id> --namespace workspace.vigie`

Expected: the Q4 audit and period rows meet all audit, metric, hash, gap, and Volume-path checks listed in Task 4, Step 4.

For each quarter, submit the following quarter only after verification succeeds. If any run fails, the audit is missing, a partial write is visible, or a candidate/hash/period differs from the design, stop and inspect the existing state before any retry. For an ambiguous submit response, reuse that attempt's token to resolve the idempotency key; use a new token only after the prior run is terminal and its partial state has been reviewed.

### Task 5: Record the Pending Review Package

**Files:**
- Modify: `docs/PNC_SOURCE_REVIEW.md`

**Interfaces:**
- Consumes: four run IDs, exact acquired report hashes, read-only verifier outputs, expected metric sets, and explicit source gaps.
- Produces: a source review section that records observed results and marks all 2022 values as pending human review.

- [ ] **Step 1: Add the 2022 staging results**

Record each quarter's run ID, issuer/source URL, acquired hash, document status, candidate metrics/values/units/context, and verifier results. Distinguish Aviva's unavailable disclosure from TD's acquired report with no standalone Insurance KPI. Include any prior period revisions observed before the run.

- [ ] **Step 2: State the review and publication boundary**

Label all 2022 values and hashes as awaiting source/accounting-basis review. State that no reviewed-evidence entries or Gold values were changed. Do not describe staging writes as cross-table atomic.

- [ ] **Step 3: Review documentation against verifier output**

Compare every listed run ID, hash, metric, value, unit, and unavailable reason with the saved JSON/SQL readback outputs. Remove any claim not directly supported by those outputs and exact acquired source content.

- [ ] **Step 4: Commit the review package**

```bash
git add docs/PNC_SOURCE_REVIEW.md
git commit -m "docs: record staged 2022 P&C evidence"
```

### Task 6: Final Verification, Review, and Integration

**Files:**
- Review all changed files in the implementation branch.

**Interfaces:**
- Consumes: Tasks 1–5 and the approved staging results.
- Produces: a CI-passing PR merged into `main`; no evidence approval or Gold publication.

- [ ] **Step 1: Run focused tests and full local gate after documentation updates**

Run the Task 3 focused test command, then `uv run --python 3.12 pytest -m "not databricks_connect and not databricks_runtime" -q`, followed by `git diff --check`.

Expected: all applicable tests pass; any environment skips are reported exactly.

- [ ] **Step 2: Review the complete diff and stage boundary**

Confirm the branch contains only the approved spec and plan, Q4 fixture coverage, the read-only verifier, focused tests, and source-review documentation. Confirm no reviewed-evidence approvals, report bytes, secrets, Gold publication code, deployment files, schedules, or Live Finance files changed.

- [ ] **Step 3: Request a focused code review**

Ask a fresh `gpt-6-luna` agent at medium reasoning effort to review candidate selection, hash checks, unsafe verifier inputs, and staging-versus-publication scope. Resolve any valid issue and rerun the relevant tests.

- [ ] **Step 4: Open the PR, wait for CI, and merge under standing authorization**

Include local verification counts, four run IDs, and the pending-human-review boundary in the PR body. Merge only after GitHub `unit-tests` passes and the final PR diff matches this plan.

- [ ] **Step 5: Verify the merged commit and preserve the source checkout**

Confirm the PR is merged and `origin/main` contains the PR merge commit. Confirm the original dirty checkout remains unchanged. Report the staged 2022 evidence as pending human review and stop before adding reviewed evidence or publishing Gold.
