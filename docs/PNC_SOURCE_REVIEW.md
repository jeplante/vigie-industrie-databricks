# P&C source review — 2026-09-20

Acquisition success is separate from publication eligibility. The latest live
run fetched all four configured reports, but no candidate has received the
report-level accounting review needed for publication.

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
with its actual period and basis.

## Publication evidence

`validate_pnc_candidate` now requires `basis_evidence`: a reviewed quarterly
basis, matching metric, value, unit, period and SHA-256; a reviewer identifier;
a report locator; and period/scope excerpts. Acquisition never creates this
approval. This is a review record, not an automatic proof of accuracy. The
future persistent workflow must restrict writes to those records accordingly.

Period hints in URLs/manifests and matching metric labels alone do not authorize
publication. Semiannual, cumulative and trailing-year evidence is rejected by
the quarterly publication gate. UI and scheduled publication remain pending.
