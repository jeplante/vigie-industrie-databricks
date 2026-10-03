# P&C 2022 Reviewed Publication Plan

> **For agentic workers:** Execute this plan task-by-task with the Superpowers workflow. Preserve the user's uncommitted primary checkout.

**Goal:** Record the user's approval for the acquired IFC and Definity 2022 quarterly evidence, then publish only those four quarters to the existing P&C Gold table.

**Architecture:** Extend the existing reviewed-only publisher with repeatable `--period` selection. Add eight exact-hash review records (three IFC metrics and six Definity metrics per quarter), dry-run those periods, then publish and verify only the selected rows.

**Tech Stack:** Python 3.12, pytest, YAML, Databricks SDK, existing Delta MERGE publisher.

**Spec:** `docs/PNC_SOURCE_REVIEW.md`, section “Historical 2022 comparative P&C staging”. The staging/backfill design is `docs/superpowers/specs/2026-10-02-pnc-2022-comparative-backfill-design.md`; it ended before human approval or Gold publication.

## Global Constraints

- Target periods are exactly `2022-Q1` through `2022-Q4`.
- Only IFC and DFY are eligible; Aviva and TD remain excluded.
- Do not change Life Finance, existing other-period Gold observations, the App, schedules, Jobs, deployment, or workspace configuration.
- Do not claim cross-table atomicity.
- Stop remote writes if account, target table, privileges, dry-run results, or existing target rows differ from the approved scope.

## Review Focus

- Invalid or duplicate period arguments must not widen publication scope.
- Missing review evidence, candidate/hash mismatch, unsupported source, or rejected metric must block publication.
- Existing Gold rows for the selected quarters must be checked for duplicates or conflicting values before writing.
- The publisher's default behavior without `--period` must remain backward compatible.
- Post-write readback must verify all selected values, provenance, and unique IDs.

---

### Task 1: Add explicit period selection to the publisher

**Files:**
- Modify: `scripts/publish_pnc_reviewed.py`
- Modify: `src/vigie_databricks/pnc_review.py`
- Test: `tests/test_pnc_review.py`

**Interfaces:**
- Add `select_reviewed_periods(reviews, periods=None)`; return matching review mappings in original order and reject invalid periods, repeated periods, or an empty selection.
- Add repeatable `--period YYYY-QN`; omitted periods preserve the existing all-reviewed behavior. Add `--profile` with the existing `jeplante` default so a temporary scoped OAuth profile can be selected without altering repository defaults.

- [x] Test selected periods include only requested evidence; no filter preserves all; invalid, duplicate, and unmatched selections raise.
- [x] Run the focused tests and verify they fail before implementation.
- [x] Implement the helper and wire CLI selection before reading candidates.
- [x] Run focused tests and publisher tests.

### Task 2: Record the approved 2022 source evidence

**Files:**
- Modify: `config/pnc/reviewed_evidence.yaml`
- Modify: `docs/PNC_SOURCE_REVIEW.md`

- [x] Add eight reviews for IFC and DFY across Q1–Q4, binding every reviewed metric to its exact acquired source hash, period, unit, value, scope, and comparative-quarter locator. Record the user approval date and reviewer identity.
- [x] Keep TD/Aviva absent from quarterly review evidence; document their exclusions.
- [x] Replace the pending-review status with the approval record, while retaining staging run IDs and the evidence provenance.
- [x] Validate YAML and assert 36 metrics with no duplicate issuer/period/hash/metric keys.

### Task 3: Validate, publish, and read back

**Files:**
- No additional product files; append publication outcome to `docs/PNC_SOURCE_REVIEW.md` after verification.

- [x] Run the Python 3.12 local test gate (`220 passed, 17 skipped`).
- [ ] Run the publisher without `--publish` and with all four explicit `--period` arguments; require exactly 36 current observations and zero rejections.
- [ ] Read-only inspect current Gold rows for the four periods and confirm no duplicate or conflicting observation IDs.
- [ ] Publish with the same four periods only after identity, Gold table, and write access are confirmed.
- [ ] Independently read back selected periods and verify 36 expected rows, unique observation IDs, exact metric/value/unit/hash/source URL, and evidence fields.
- [ ] Record the Gold readback in the review ledger and run `git diff --check`.

**Execution note (2026-10-03):** The local publisher dry-run could not authenticate because the Databricks OAuth token cache is absent. A temporary CLI login is pending. Remote verification and the Gold write are not complete. Confirm the authenticated principal and `MODIFY` on `workspace.vigie.pnc_gold_observations` before proceeding; the currently supplied grants show staging-table privileges only.
