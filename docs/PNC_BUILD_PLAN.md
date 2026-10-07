# P&C build — phase 1

The P&C domain is isolated from the life-insurance domain. Its initial issuer cohort is IFC, AV, TD and DFY.

## Disclosure basis

| Company | Basis |
| --- | --- |
| IFC | Consolidated global P&C group (Canada, UK&I and US) |
| DFY | Canadian P&C group |
| AV | Canada segment of Aviva plc |
| TD | TD Insurance segment of TD Bank Group |

## Publication rules

- A KPI is published only when its official report, period, unit and reporting basis are all traceable.
- An unavailable or non-comparable KPI remains N/A; it is never inferred from a consolidated figure.
- P&C raw files, audit tables and Gold tables remain separate from the life domain.
- Live collection is disabled until source and extraction validation succeeds for all four issuers.

## Historical evidence checkpoint (recorded 2026-09-28)

Nine period manifests from 2023-Q1 through 2025-Q1 and 21 issuer-period
review records document 84 quarterly metrics: 10, 9, 9, 9, 10, 9, 9, 9 and
10 by period. They preserve Aviva's unsupported non-Q1 quarters, TD's
combined Wealth Management and Insurance gaps, fiscal versus calendar closes,
and the exclusion of trailing-period ROE. See `PNC_SOURCE_REVIEW.md` for
period coverage and `config/pnc/reviewed_evidence.yaml` for hash-bound values.

Historical run notes report reviewed-only dry-runs, Gold MERGEs and independent
SQL readbacks ending at 131 rows and 131 distinct observation IDs after
2023-Q1 was added. These are dated reports of prior runs, not a fresh check of
the live Volume, staging tables or Gold table. The current checkout contains
review evidence; a new publication decision requires exact stored-byte and
candidate readback, the reviewed-only dry-run, and independent Gold readback.
Acquisition and publication remain manual and unscheduled.

## Observed state checkpoint (read-only, 2026-10-06)

Read-only SQL readback of `workspace.vigie.pnc_gold_observations`: 167 rows
across 18 quarters, 2022-Q1 through 2026-Q2 (9 or 10 rows per quarter, two or
three issuers each). 2026-Q2 holds nine rows for IFC, TD and DFY; DFY's five
metrics there do not include `insurance_revenue`. The reviewed evidence on
`main` now records DFY 2026-Q2 `insurance_revenue` = 1.7937 (CAD billions;
reviewed 2026-09-28), but that value has not been published to Gold: doing so
is a separate, explicitly authorized publication. `vigie-pnc-acquisition-review`
has no schedule; its last two runs (2026-09-20 and 2026-09-21) ended `FAILED`
in `pnc_acquire`. Acquisition and publication remain manual.

Since the earlier checkpoints: the 2022 comparative backfill was published
(PR #17), 2026-Q2 acquisition sources were added (PR #20), and the App renders
P&C through the shared presentation module with the same page skeleton as the
life universe (PR #18, #22). `PNC_PREVIEW_ENABLED` remains the activation gate.
Aviva Canada stays `N/A` outside Q1 (no isolated Canada quarterly COR) and TD
Insurance stays gap-flagged where TD reports a combined Wealth Management and
Insurance segment. This is a dated observation, not a standing guarantee.

## Original phase-1 implementation slices (historical)

The list below records the initial build plan; the dated checkpoint above
documents later historical review and publication claims.

1. Source discovery and document provenance dry-run. **Manifest checks only:**
   the source manifest covers IFC, AV, TD and DFY, and each URL is checked
   against its issuer allowlist. This is not a live acquisition dry-run.
2. Deterministic extraction fixtures from official reports. **In progress:**
   candidate extraction is isolated, while a provenance gate rejects a TD
   combined Wealth Management and Insurance figure even when it comes from an
   official TD report.
3. P&C Bronze/Silver/Gold tables and validation gates. **Local validation and
   batch publication decisions implemented; storage and workflow remain to
   build.** Publication rejects an entire invalid batch, retains prior history,
   and merges valid observations idempotently. Period/accounting-basis evidence
   still needs verification against actual report contents before deployment.
4. Historical backfill from 2022-Q1.
5. App domain selector and P&C comparison presentation.

## Evidence fixture policy

### Persistent staging result and cache follow-up

Job `313136866676385`, run `929141499807355`, completed with the expected
`extraction_incomplete` failure: four documents and eight candidates persisted,
with AV missing and zero model calls. All three P&C staging tables were created.
No Gold publication occurred.

Version 0.10.1 fixes the persistent entry point to load the most recent usable
document revision before acquisition, enabling ETag/Last-Modified requests.
Selection is deterministic and excludes failed or pathless document records.
Local P&C verification: 26 tests passed. Version 0.10.1 is deployed; run
1118191037742165 reused unchanged TD and DFY content and retained eight review
candidates. It ended with the expected `extraction_incomplete` status for AV.

Direct SQL verification on 2026-09-21 (statement
01f1b5ae-1afe-1d8d-bdbc-82d8d9328f93) found:

| Table / company | Rows | Distinct keys | Content revisions |
| --- | ---: | ---: | ---: |
| Candidates / TD | 1 | 1 | 1 |
| Candidates / DFY | 6 | 6 | 1 |
| Candidates / IFC | 3 | 3 | 3 |
| Documents / TD | 1 | 1 | 1 |
| Documents / DFY | 1 | 1 | 1 |
| Documents / IFC | 3 | 3 | 3 |
| Documents / AV | 4 | 4 | 4 |

Two distinct run audits report `extraction_incomplete`, eight candidates each.
TD/DFY unchanged-content idempotence is confirmed. IFC/AV retain distinct raw
revisions; these totals alone do not establish which execution created each
revision. Candidate keys are unique; multiple versions of one observation are
intentional staging history and must not be counted as multiple Gold values.
The read-only check is reproducible with `scripts/verify_pnc_staging.py`.

### Remote execution preparation

Package version 0.10.0 includes the P&C acquisition entry point. The template
`databricks_pnc_acquire_job.template.json` defines a manual-only acquisition job,
with no retries and a ten-minute timeout. Replace `<workspace-path>` with the
uploaded package/config location. The configured raw volume must already exist
and the job identity needs write access to it and the target schema.

Remote verification on 2026-09-20 stopped at `current-user me`: profile
`jeplante` returned an invalid OAuth refresh token. No remote job or table was
created. Reauthenticate with `databricks auth login --profile jeplante`, then
verify identity and volume/schema access before uploading and running the job.
The current Aviva extraction gap means this job is expected to persist a
diagnostic audit and exit unsuccessfully; that is not a publication-ready run.

The bounded acquisition command is now available locally:

```powershell
python -m vigie_databricks.tasks.pnc_acquire --config-directory config/pnc --manifest tests/fixtures/pnc_source_manifest.yaml --allow-network
```

It fetches at most one document per issuer, reports per-source errors, verifies
content hashes and emits candidates requiring review. It does not publish,
schedule a job, or treat a manifest period as verified report evidence. Live
Databricks staging is implemented, but has not yet been exercised remotely.
Run the same command inside Databricks with `--persist --run-id <job-run-id>`
to persist content in the configured P&C volume and upsert
`workspace.vigie.pnc_financial_documents`, `pnc_candidates` and `pnc_run_audit`.
`--namespace catalog.schema` supports a different target namespace. This mode
does not publish Gold. Acquisition errors and missing extraction coverage are
audited before the command fails. Writes are sequential Delta upserts, not a
transaction across tables; a storage error may leave a partial staging run.
Document revisions and extraction revisions are retained through content-based
identifiers. No schedule is enabled by this command.

### Live verification, 2026-09-20

Two bounded acquisition runs fetched all four manifest documents without AI.
The first exposed cumulative Definity income values incorrectly labelled as
quarterly candidates. HTML parsing now handles inline labels and skips hidden
metadata and footnote markers. Year-to-date narrative amounts are excluded.
The second run extracted Definity quarterly operating income of CAD 118.0m
and net income of CAD 152.4m, replacing the incorrect cumulative candidates.
Eight candidates were produced across IFC, TD and DFY; AV produced none.
The command correctly returned `extraction_incomplete` with exit code 1.
No observations were published. Acquisition coverage is 4/4; financial
validation coverage is not 4/4. Aviva source selection, accounting-basis
verification (including trailing ROE), persistent storage and UI remain open.

The repository records source URLs, reporting periods and disclosure scopes in
`tests/fixtures/pnc_source_manifest.yaml`; it does not commit issuer PDFs.
Each live acquisition must record its content hash, ETag, Last-Modified value
and raw-file path before an extraction candidate can be validated. This keeps
the test suite reproducible without redistributing issuer reports.
