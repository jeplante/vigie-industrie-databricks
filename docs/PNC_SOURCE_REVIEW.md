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

## Historical Q4 2025 review and publication — 2026-09-24

`config/pnc/history/2025-Q4.yaml` explicitly marks Aviva as having no
Canada-quarter disclosure; its [FY 2025 statement](https://www.aviva.ca/en/press-releases/2026/full-year-2025-results/)
reports a 95.6% **annual** Canada COR, which is not a Q4 KPI. The bounded
acquirer skipped that annual document. Two local reads of the three quarterly
sources returned stable hashes, eleven candidates and zero AI calls. The
one-time staging run `870566534049261` persisted three raw documents and
eleven candidates; its task status was `FAILED` by the expected four-source
completeness gate (`AV` missing), not by a download or storage error.

| Official source and actual close | Reviewed Q4 values | SHA-256 |
| --- | --- | --- |
| [Intact consolidated](https://newsroom.intactfc.com/2026-02-10-Intact-Financial-Corporation-reports-Q4-2025-results?asPDF=1), Dec 31 | Combined ratio 85.9%; operating net income attributable to common shareholders CAD 979m; IFRS net income CAD 961m | `8b98bc8d6d84f9d6b3d8049680d5496e7b6e10b5aa5a319e24456f386b7589cf` |
| [TD Insurance](https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2025/q4/q4-2025-news-release-en.pdf), fiscal Oct 31 | Standalone Insurance net income CAD 142m, not the CAD 699m combined Wealth Management and Insurance segment | `83a53de263f050485d215e725cb4a487f88114b7e9041887a17d228755b59b1d` |
| [Definity consolidated](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2026/Definity-Reports-Fourth-Quarter-and-Full-Year-2025-Results/default.aspx), Dec 31 | Combined ratio 89.9%; claims ratio 60.6%; expense ratio 29.3%; operating net income CAD 120.7m; net income attributable to common shareholders CAD 58.0m | `0a8b6a70344c9ca3b0e7b96770d0bf5ef130983bd04fcb684680f9a7905ceb2d` |

Intact's Q4 column was distinguished from its full-year column; the PDF
rendering is used for byte-stable provenance. Definity's report also has
separate Q4 and full-year columns. Intact's 19.5% and Definity's 12.2%
operating ROE figures are trailing-year measures, so both candidates were
rejected. The nine remaining Q4 candidates passed exact-hash, scope, period,
unit and value review. A publisher dry-run accepted 27 total observations.
Two reviewed-only Gold MERGEs succeeded. Independent SQL readback found
27 rows and 27 distinct IDs: nine each for Q4 2025, Q1 2026 and Q2 2026;
zero Aviva rows and zero operating ROE rows. Q4 close dates are preserved as
Dec 31 for Intact/Definity and fiscal Oct 31 for TD. No schedule was enabled.

## Historical Q3 2025 review and publication — 2026-09-25

`config/pnc/history/2025-Q3.yaml` uses official releases for Intact, TD and
Definity. The [Aviva Q3 trading update](https://www.aviva.com/newsroom/news-and-research-overview/news-releases/2025/11/Q32025-trading-update/)
gives Canada GI premiums for **nine months** in GBP and a **Group** COR, not
an isolated Canadian Q3 result. Aviva is explicitly unavailable for this
quarter; neither figure is inserted into quarterly CAD Gold.

| Official source and actual close | Reviewed Q3 values | SHA-256 |
| --- | --- | --- |
| [Intact consolidated](https://newsroom.intactfc.com/2025-11-04-Intact-Financial-Corporation-reports-Q3-2025-results?asPDF=1), Sep 30 | Combined ratio 89.8%; net operating income attributable to common shareholders CAD 797m; IFRS net income CAD 861m | `3918131d805d3a7a5f0627aa21489c753df6729f9846ae0c4b1294aff926310a` |
| [TD Insurance](https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2025/q3/q3-2025-news-release-en.pdf), fiscal Jul 31 | Standalone Insurance net income CAD 182m, not the CAD 703m combined Wealth Management and Insurance segment or CAD 577m nine-month Insurance total | `5173862dcd68797d7b010ccda5e64ee47f14ad5bf5f34ac4789460810a14b5f6` |
| [Definity consolidated](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2025/Definity-Financial-Corporation-Reports-Third-Quarter-2025-Results/default.aspx), Sep 30 | Insurance revenue CAD 1,183.6m; combined ratio 89.4%; claims ratio 60.2%; expense ratio 29.2%; operating net income CAD 125.2m; net income attributable to common shareholders CAD 193.1m | `f25fa778e6be1837c70de8d0716a0c7b7daeb5c73072643a7944016c5494647e` |

TD's Q3 PDF plain-text extraction split words and `$521` across line breaks.
The P&C TD PDF path now uses pypdf's layout mode; the generic finance path and
the other P&C issuers retain plain mode. Tests guard against substituting
the combined segment or nine-month result. Definity's insurance revenue is
read only from the current-quarter CAD-millions column, never the YTD column.
Definity's 12.5% operating ROE and Intact's 19.6% operating ROE are trailing
12-month measures and remain excluded.

The one-time staging run `1081049020047427` persisted three raw documents
and 11 candidates. Its audit reports `extraction_incomplete`, missing `AV`,
empty errors and zero AI calls. The task failed on the expected four-source
completeness gate; no P&C schedule was enabled. Exact-hash review approved ten
Q3 observations and rejected Definity's trailing ROE. The reviewed-only
publisher accepted 37 total rows (including 27 previously published), and
two Gold MERGEs completed. Independent SQL readback returned 37 rows with 37
distinct IDs: ten Q3, nine Q4, nine Q1 2026 and nine Q2 2026. No Aviva or
operating ROE row was published. TD's July 31 fiscal close is preserved.

## Historical Q2 2025 review and publication — 2026-09-25

`config/pnc/history/2025-Q2.yaml` covers the three acquirable official
quarterly reports. The [Aviva HY25 report](https://www.aviva.com/newsroom/news-and-research-overview/news-releases/2025/08/HY2025-results-announcement/)
reports a 94.7% **half-year** Canada COR and GBP-denominated half-year Canada
premiums, not isolated Q2 Canadian-quarter figures. Aviva remains N/A for Q2.

| Official source and actual close | Reviewed Q2 values | SHA-256 |
| --- | --- | --- |
| [Intact consolidated](https://newsroom.intactfc.com/2025-07-29-Intact-Financial-Corporation-reports-Q2-2025-results?asPDF=1), Jun 30 | Combined ratio 86.1%; net operating income attributable to common shareholders CAD 935m; IFRS net income CAD 867m | `2cd9ee3f3816f04a27638456d699d0631158dff90a2365ab1ef0198a89032ff5` |
| [TD Insurance](https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2025/q2/2025-q2-earnings-newsrelease-en.pdf), fiscal Apr 30 | Standalone Insurance net income CAD 227m, not the CAD 707m combined Wealth Management and Insurance result or CAD 395m six-month total | `496491f7b0c283f7d0806d77a59378f0becd8c929339428ec49f7d3f5dae4779` |
| [Definity consolidated](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2025/Definity-Reports-Second-Quarter-2025-Results/), Jun 30 | Insurance revenue CAD 1,162.1m; combined ratio 92.9%; claims ratio 63.2%; expense ratio 29.7%; operating net income CAD 98.9m; net income attributable to common shareholders CAD 75.1m | `4d3be5101e2d6f77e90b97a06dd466a3aa311bacf2fa69a59fa5e425f2f5abf1` |

Two bounded local acquisitions returned identical document hashes and 12
candidates, with no fetch errors or AI calls. Intact's 16.3% and Definity's
9.6% operating ROE are trailing-12-month measures and were rejected. The
one-time staging run `117048652549415` persisted three documents and 12
candidates; its audit shows only `AV` missing, empty errors and zero AI calls.
The run failed under the former four-source gate despite the explicit Aviva
unavailable declaration. Subsequent code treats an explicitly unavailable
source as an audited gap but does not fail acquisition; an unexpectedly missing
acquirable source still fails. This fix was locally tested but was not part of
the Q2 staging wheel (`0.10.5`).

Exact-hash review approved ten Q2 values. The reviewed-only publisher accepted
47 total observations, including the prior 37. Two Gold MERGEs succeeded;
independent SQL readback found 47 rows and 47 unique IDs: ten each for Q2 and
Q3 2025, nine each for Q4 2025, Q1 2026 and Q2 2026. Aviva and operating
ROE have zero published rows. TD's April 30 fiscal close is preserved. The
App's P&C reader queries Gold directly, but the App runtime was `STOPPED`
(`workspace or account status`) on this date, so browser visibility was not
verified. No P&C schedule was enabled.

## Historical 2023-Q1 through 2025-Q1 review records (2026-09-26 to 2026-09-28)

The nine period manifests under `config/pnc/history/` declare one source or
explicit unavailability for each issuer. The 21 new records in
`config/pnc/reviewed_evidence.yaml` identify the reviewed quarterly values by
company, period, exact document hash, accounting basis, close date, disclosure
scope and unit. They contain 84 metric entries. Each record's document hash
matches the hash stated in the historical source-review notes used to prepare
this checkpoint; this local comparison cannot recheck the stored raw bytes.

| Quarter | Official source | Reviewed document SHA-256 |
| --- | --- | --- |
| 2023-Q1 | [AV](https://static.aviva.io/content/dam/aviva-corporate/documents/investors/pdfs/results/2023/Aviva-Q1-trading-update.pdf) | `a56efedf46af8949cc0277fcfe765430c96ec69f94d3f25dbdd5297c4f70a64d` |
| 2023-Q1 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2023/Definity-Reports-First-Quarter-2023-Results/default.aspx) | `f1cc73baaa89e1fdd2330c6dede76254f931ca8f3bc262b056affc344252ac92` |
| 2023-Q1 | [IFC](https://newsroom.intactfc.com/2023-05-10-Intact-Financial-Corporation-reports-Q1-2023-results-under-IFRS-17?asPDF=1) | `dd3cd085461c3b980b04a45acd4f143faf762955632eb25ad5cfd21c7ed78df5` |
| 2023-Q2 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2023/Definity-Financial-Corporation-Reports-Second-Quarter-2023-Results/default.aspx) | `d9689d8611360a3b365b3fd79714116dacedf05b777000cf810a7e7cfc573418` |
| 2023-Q2 | [IFC](https://newsroom.intactfc.com/2023-08-02-Intact-Financial-Corporation-reports-Q2-2023-results?asPDF=1) | `a442faa1e1a1d0e0799ebcccd781303a52bcb9b78b2b898f6e844f31db93806e` |
| 2023-Q3 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2023/Definity-Reports-Third-Quarter-2023-Results/default.aspx) | `d75cc118541a1474eca34e54daef442ca952922c0ef21c4927544ffd7c19575b` |
| 2023-Q3 | [IFC](https://newsroom.intactfc.com/2023-11-07-Intact-Financial-Corporation-reports-Q3-2023-results?asPDF=1) | `e0fcbb66703a0bcb81acd95ac97621d8cea72df6268957ec79314f965b3b670e` |
| 2023-Q4 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2024/Definity-Financial-Corporation-Reports-Fourth-Quarter-and-Full-Year-2023-Results/default.aspx) | `f2df994386d649b1075f89d10d77c5ec72c8cc691606589e9e6f395925738270` |
| 2023-Q4 | [IFC](https://newsroom.intactfc.com/2024-02-13-Intact-Financial-Corporation-reports-Q4-2023-results?asPDF=1) | `177e57ec7ddd2a3273a4c1f05d99f8105a872c34bdaa877eff0f700c22fdaf25` |
| 2024-Q1 | [AV](https://static.aviva.io/content/dam/aviva-corporate/documents/investors/pdfs/results/2024/Aviva-Q1-2024-trading-update.pdf) | `f88fb13f40902924228b042be607c8fbf5d726242dc67fe11dd3a44bd2f9ecb7` |
| 2024-Q1 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2024/Definity-Reports-First-Quarter-2024-Results/default.aspx) | `a5acd71e170a2b1f303f33cc7145e0ccd80e84c03a1ccc9819b0fd20ad13f46d` |
| 2024-Q1 | [IFC](https://newsroom.intactfc.com/2024-05-07-Intact-Financial-Corporation-reports-Q1-2024-results?asPDF=1) | `8eb420428bc553474501c10ac16e9e4edbbc050d57ff3b952fbe7b54822ff260` |
| 2024-Q2 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2024/Definity-Reports-Second-Quarter-2024-Results/default.aspx) | `3500bda8efda90d48337b290c5f4f9ba1aefb3236e4d9a76180c843a283077b6` |
| 2024-Q2 | [IFC](https://newsroom.intactfc.com/2024-07-30-Intact-Financial-Corporation-reports-Q2-2024-results?asPDF=1) | `da5e14b57925bc6b1e092dd5fb153f57e7c26e4cac8697a424d98d2f61b9e57d` |
| 2024-Q3 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2024/Definity-Reports-Third-Quarter-2024-Results/default.aspx) | `2bcd9fdfccee8cc790f88515a1659b16df52000762079e76ad86bff8ded93f7e` |
| 2024-Q3 | [IFC](https://newsroom.intactfc.com/2024-11-05-Intact-Financial-Corporation-reports-Q3-2024-results?asPDF=1) | `678963a4e33716639ab2afe7d5d65202d7aa34ffc34dc383d39bf44a7f77b7ce` |
| 2024-Q4 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2025/Definity-Financial-Corporation-Reports-Fourth-Quarter-and-Full-Year-2024-Results/default.aspx) | `12bc5301e82ddd1f0460fa89bfeaa2478b2aab12462c08345162f16f2acd18f6` |
| 2024-Q4 | [IFC](https://newsroom.intactfc.com/2025-02-11-Intact-Financial-Corporation-reports-Q4-2024-results?asPDF=1) | `70c68bf0c2f94a6c51cd3a914650bfc9fa0ca3f0750e3c57a771c9509b121d95` |
| 2025-Q1 | [DFY](https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2025/Definity-Reports-First-Quarter-2025-Results/default.aspx) | `13358d597bf1d55cc2677279bafb1f2e4f7a9b638f1ddd0aa037c3dc2b800b7f` |
| 2025-Q1 | [IFC](https://newsroom.intactfc.com/2025-05-06-Intact-Financial-Corporation-reports-Q1-2025-results?asPDF=1) | `ca58370db819c1c3356155ddac40bf001667afbf1426c9a80543271605ce11bc` |
| 2025-Q1 | [TD](https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2025/q1/2025-q1-earnings-newsrelease-en.pdf) | `0d6f9821f369c50cf577807fc1edf0d461d3185834ba6df2d649b94a31e543df` |

| Quarter | Reviewed issuer metrics | Explicit quarterly gaps | Historical new Gold rows |
| --- | --- | --- | ---: |
| 2023-Q1 | IFC 3, AV 1, DFY 6 | TD combined segment only | 10 |
| 2023-Q2 | IFC 3, DFY 6 | AV half-year; TD combined segment | 9 |
| 2023-Q3 | IFC 3, DFY 6 | AV nine-month Group result; TD combined segment | 9 |
| 2023-Q4 | IFC 3, DFY 6 | AV full-year; TD combined segment | 9 |
| 2024-Q1 | IFC 3, AV 1, DFY 6 | TD combined segment only | 10 |
| 2024-Q2 | IFC 3, DFY 6 | AV half-year; TD combined segment | 9 |
| 2024-Q3 | IFC 3, DFY 6 | AV nine-month Group result; TD combined segment | 9 |
| 2024-Q4 | IFC 3, DFY 6 | AV full-year; TD combined segment | 9 |
| 2025-Q1 | IFC 3, TD 1, DFY 6 | AV Group ratio and rounded GBP Canada premiums | 10 |

IFC's selected combined ratio is consolidated and undiscounted across its
geographies; it is not a Canada segment ratio. AV's reviewed Q1 combined
operating ratios are undiscounted Canada General Insurance figures. TD's
2025-Q1 Insurance income belongs to its fiscal quarter ended 2025-01-31;
calendar reporters closed 2025-03-31. Definity's 2023-Q3 net loss is
`-0.0483 CAD_BILLION` (CAD -48.3 million). Monetary review values use
`CAD_BILLION`; ratio values use `PERCENT`. Annual, half-year, nine-month,
combined-segment and trailing-year ROE figures remain absent from these
quarterly review metrics.

The source-review notes recorded bounded unscheduled staging runs and
reviewed-only publication readbacks on 2026-09-26 to 2026-09-28. The reported
period totals rose from 47 rows before this slice to 131 rows and 131 distinct
observation IDs after the 2023-Q1 addition. That is historical evidence, not a
fresh live verification. This checkout does not independently establish the
Volume hashes, persisted candidate payloads, current Gold counts or deployed
parser version. The historical notes describe parser corrections in local code
changes outside this evidence-only branch; the manifests and reviews alone do
not reproduce those staging runs from the current `origin/main` code. Recheck
those against the live workspace before any further publication or present-day
operational claim.
