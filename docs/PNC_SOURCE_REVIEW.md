# P&C source review — 2026-09-20

Acquisition success is separate from publication eligibility. The latest live
run fetched all four configured reports. Nine observations subsequently
received report-level accounting review and were published; the remaining
candidates are not eligible for the quarterly Gold table.

## Aviva

Official Canada release:
https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/

Group financial review:
https://www.aviva.com/newsroom/news-and-research-overview/news-releases/2026/08/half-year-2026-results-announcement/

The Canada combined operating ratio is 93.0% for HY26. This is a six-month
ratio, not an isolated Q2 ratio. Group financial monetary figures are reported
in GBP; the Canadian segment is not automatically denominated in CAD.
Do not populate quarterly CAD KPIs with these figures or derive a Q2 ratio by
subtracting Q1. The quarterly comparison remains N/A until comparable evidence
is available. A future separate half-year presentation can retain this fact
with its actual period and basis. On 2026-09-23, the official Q1 2026 trading
update and the HY26 financial results pack were also checked. Q1 reports
Canada GI gross written premiums (in rounded GBP) but only a Group COR; the
pack's Canada general-insurance table labels its figures as six months 2026.
Neither establishes a separately published Canadian Q2 COR, and subtracting
rounded premiums would not recover that rate. The App links the official HY26
Canada release next to Aviva's quarterly N/A, without inserting its HY ratio
into quarterly Gold.

## Publication evidence

## Stored-report review, 2026-09-21

Five DFY quarterly observations were checked against the stored consolidated
table. The operating ROE remains excluded because the narrative defines it over
twelve months. IFC's reviewed 94.9% combined ratio is global consolidated;
the Canada row is 91.7% and must not be substituted without changing scope.
TD's 279 million CAD Insurance net income is verified on page 21, but its
fiscal Q2 ends April 30, unlike the June 30 calendar quarters. Evidence records
retain `period_end`, `calendar_basis` and `disclosure_scope`; the eventual UI
must display these distinctions. Only the exact reviewed hashes are eligible.
On 2026-09-22, seven reviewed observations were published to
`workspace.vigie.pnc_gold_observations` using `scripts/publish_pnc_reviewed.py`.
Readback matched all seven values and their full evidence records, with unique
observation IDs. Initially IFC had one global consolidated ratio, TD one
fiscal-quarter Insurance net income, and DFY five calendar-quarter metrics. Unreviewed rows,
DFY trailing ROE and Aviva were not published. On 2026-09-23, the App service
principal received SELECT on the new Gold table and `vigie-gold-viewer` was
deployed successfully with the P&C view enabled. The App was RUNNING after
deployment, but this does not guarantee continuous availability on the current
Databricks workspace. Gold readback before the IFC net-income backfill returned
exactly seven `validated_quarterly` rows: DFY five, IFC one and TD one. The P&C view warns
that TD's fiscal Q2 closed on April 30, while the published IFC and DFY
calendar Q2 values closed on June 30.

On 2026-09-23, the stored IFC report revision above was rechecked against its
SHA-256 and the issuer's Consolidated Highlights. The Q2-2026 first-column
`Net income` value is CAD 720 million (0.720 billion); the H1 value is CAD
1,472 million and was not used. A table-scoped deterministic extractor now
produces this candidate. `scripts/stage_ifc_highlights.py` staged only this
candidate, with exact-hash readback. Its explicit review has the same global
consolidated scope and June 30 quarter end as IFC's combined ratio. Publication
dry-run accepted eight reviewed observations. Two Gold MERGEs succeeded; a
subsequent count returned eight rows, eight distinct observation IDs and one
IFC net-income row. Aviva and the other unsupported KPIs remain unpublished.

The same IFC Consolidated Highlights first Q2-2026 column reports CAD 561
million of **net operating income attributable to common shareholders**. This
is a non-IFRS measure, not Intact's underwriting income or the CAD 720 million
IFRS net income. It was extracted from the hash-checked stored report, matched
to the issuer's published table, reviewed with the same June 30 and global
consolidated scope, staged via `scripts/stage_ifc_highlights.py --metric
operating_income --persist`, and published on 2026-09-23. Two Gold MERGEs
left nine rows with nine unique IDs, including one IFC operating-income row.
The App and P&C metric contract now label `operating_income` as "Résultat net
opérationnel"; Definity's CAD 118 million is also operating **net** income.
Both are company-defined non-IFRS measures, so cross-issuer differences in
adjustments must be checked in the linked reports.

`validate_pnc_candidate` now requires `basis_evidence`: a reviewed quarterly
basis, matching metric, value, unit, period and SHA-256; a reviewer identifier;
a report locator; and period/scope excerpts. Acquisition never creates this
approval. This is a review record, not an automatic proof of accuracy. The
future persistent workflow must restrict writes to those records accordingly.

Period hints in URLs/manifests and matching metric labels alone do not authorize
publication. Semiannual, cumulative and trailing-year evidence is rejected by
the quarterly publication gate. The P&C UI reads only reviewed Gold rows; a
scheduled P&C publication workflow remains pending.
