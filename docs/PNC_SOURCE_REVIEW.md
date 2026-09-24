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
The official [HY26 Excel results-pack tables](https://static.aviva.io/content/dam/aviva-corporate/documents/investors/excel/results/2026/aviva-plc-half-year-2026-financial-results-pack-tables.xlsx)
were checked on 2026-09-23 as well. Worksheet A1 labels Canada personal,
commercial and total columns **6 months 2026**; the 93.0% undiscounted COR
is in total-Canada cell J30 on that six-month basis. The other Canada rows
checked (B1 operating profit, B4 controllable costs, C1 cash remittances,
C2 own-funds generation) likewise use six-month or full-year columns.
This workbook does not support publishing an isolated Canada Q2 ratio or
quarterly monetary KPI.

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
The publication gate also rejects an excerpt naming six months, a half-year,
year-to-date or full-year period even if the review field says `quarterly`.
An explicit quarter must match the observation period; a three-month excerpt
must name the reporting year. This is a conservative text check, not a
substitute for the report-level accounting review.

Period hints in URLs/manifests and matching metric labels alone do not authorize
publication. Semiannual, cumulative and trailing-year evidence is rejected by
the quarterly publication gate. The P&C UI reads only reviewed Gold rows; a
scheduled P&C publication workflow remains pending.

## Historical Q1 2026 review — 2026-09-24

`config/pnc/history/2026-Q1.yaml` identifies one official Q1 document for each
issuer. A bounded local dry-run fetched four documents with zero AI calls.
It produced ten candidates. Nine passed exact-hash, period, scope and value
review; Definity's 13.0% operating ROE is a **trailing 12-month** measure and
was deliberately excluded. Aviva's [Q1 trading update](https://www.aviva.com/newsroom/news-and-research-overview/news-releases/2026/05/Q12026-trading-update/)
reports rounded Canadian premiums in GBP and a **Group**, not Canada, COR;
it supplies no comparable quarterly Canada KPI for this Gold view.

| Source and basis | Reviewed Q1 observations |
| --- | --- |
| [Intact](https://newsroom.intactfc.com/2026-05-05-Intact-Financial-Corporation-reports-Q1-2026-results?asPDF=1), global consolidated, March 31 | Combined ratio 91.3%; net operating income attributable to common shareholders CAD 770m; IFRS net income CAD 752m |
| [TD Insurance](https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2026/q1/2026-q1-report-shareholders-en.pdf), fiscal January 31 | Standalone Insurance net income CAD 183m, not the combined Wealth Management and Insurance CAD 757m |
| [Definity](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2026/Definity-Financial-Corporation-Reports-First-Quarter-2026-Results/default.aspx), March 31 | Combined ratio 92.9%; claims ratio 62.4%; expense ratio 30.5%; operating net income CAD 118.1m; net income attributable to common shareholders CAD 63.9m |

The first live extraction incorrectly selected Intact's 84.4% Canada personal
property ratio. Its extractor now requires the explicitly labelled
`Consolidated Highlights` current-quarter row; the same table supplies its
two income metrics. The HTML press-release bytes changed across requests,
so Q1 uses Intact's official PDF rendering, which returned the same SHA-256
`6f92f8b966e6566aaa82baa5888a9a86f6e4fad7d96b425ef9948d73bed808b7`
on repeated bounded requests. TD's standalone CAD 183m is extracted from
the Q1 quarterly-comparison paragraph, not the combined segment table.
The review records are in `config/pnc/reviewed_evidence.yaml`. The one-time
Databricks staging run `570585770938578` persisted four raw documents and ten
candidates with zero AI calls. Its task status was `FAILED` by the source
completeness gate because Aviva contributed no comparable Canada-quarter KPI;
the run reported no download or storage error. Exact-hash staging review
validated nine Q1 candidates, rejected the trailing-year ROE, and left Aviva
at N/A.

The reviewed-only publisher completed twice. An independent Gold readback
found 18 observations and 18 distinct observation IDs: nine for Q1 and nine
for Q2 2026, with no Aviva row or trailing-year ROE. Counts were unchanged
on the second publication. The App now exposes these rows in a separate
historical table with period, actual close, fiscal/calendar basis and official
document link; its headline comparison remains fixed to the latest quarter.
The existing `vigie-gold-viewer` App was restarted and its snapshot deployment
`01f1b80f315a14188d366276560e9bda` reached `SUCCEEDED` / `RUNNING` on
2026-09-24. This verifies deployment state, not a browser-level visual check.
No P&C acquisition or publication schedule was activated.

## Q4 2025 source reconnaissance — not yet published

The next historical quarter has official source candidates, but no Q4 2025
document hash or extracted value has been reviewed or published yet:

| Issuer | Official source candidate | Basis to verify |
| --- | --- | --- |
| Intact | [Q4 2025 results](https://newsroom.intactfc.com/2026-02-10-Intact-Financial-Corporation-reports-Q4-2025-results) | Consolidated Q4 column, not full-year column |
| TD Insurance | [Q4 2025 earnings release](https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2025/q4/q4-2025-news-release-en.pdf) | Standalone Insurance net income for fiscal quarter ended October 31, not Wealth Management and Insurance combined |
| Definity | [Q4 and FY 2025 results](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2026/Definity-Reports-Fourth-Quarter-and-Full-Year-2025-Results/default.aspx) | Q4 column, not full-year column |
| Aviva Canada | [FY 2025 Canada statement](https://www.aviva.ca/en/press-releases/2026/full-year-2025-results/) | **Annual only**; 95.6% Canada COR must not be labeled Q4 |

The three quarterly candidates require bounded acquisition, exact-document
review and a reproducible staging check before any Q4 Gold publication.
The existing four-source completeness gate cannot be satisfied by relabeling
Aviva's annual result as quarterly; Aviva remains N/A for Q4 absent a genuine
Canada-quarter disclosure.
