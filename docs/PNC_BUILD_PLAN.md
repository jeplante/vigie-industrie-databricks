# P&C build — phase 1

The P&C domain is isolated from the life-insurance domain. Its initial issuer cohort is IFC, AV, TD and DFY.

## Disclosure basis

| Company | Basis |
| --- | --- |
| IFC | Canadian P&C group |
| DFY | Canadian P&C group |
| AV | Canada segment of Aviva plc |
| TD | TD Insurance segment of TD Bank Group |

## Publication rules

- A KPI is published only when its official report, period, unit and reporting basis are all traceable.
- An unavailable or non-comparable KPI remains N/A; it is never inferred from a consolidated figure.
- P&C raw files, audit tables and Gold tables remain separate from the life domain.
- Live collection is disabled until source and extraction validation succeeds for all four issuers.

## Next implementation slices

1. Source discovery and document provenance dry-run. **Completed locally:** the
   official-source manifest covers IFC, AV, TD and DFY, and each URL is checked
   against its issuer allowlist.
2. Deterministic extraction fixtures from official reports. **In progress:**
   candidate extraction is isolated, while a provenance gate rejects a TD
   combined Wealth Management and Insurance figure even when it comes from an
   official TD report.
3. P&C Bronze/Silver/Gold tables and validation gates. **Validation gate
   completed locally; storage and workflow remain to build.**
4. Historical backfill from 2022-Q1.
5. App domain selector and P&C comparison presentation.

## Evidence fixture policy

The repository records source URLs, reporting periods and disclosure scopes in
`tests/fixtures/pnc_source_manifest.yaml`; it does not commit issuer PDFs.
Each live acquisition must record its content hash, ETag, Last-Modified value
and raw-file path before an extraction candidate can be validated. This keeps
the test suite reproducible without redistributing issuer reports.
