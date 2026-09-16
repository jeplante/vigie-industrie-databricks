# P&C source discovery — initial evidence

This document records the discovery boundary before live collection is enabled.

| ID | Official source | Usable disclosure | Initial decision |
| --- | --- | --- | --- |
| IFC | Intact Financial investor results and newsroom | Quarterly results, underwriting and catastrophe metrics | Eligible for extraction fixtures |
| AV | Aviva plc results and reports | Global reports with Canada segment disclosure | Eligible only for explicitly labelled Canada metrics |
| TD | TD quarterly reports and insurance disclosure | Insurance values within Wealth Management and Insurance; separate catastrophe notices | Eligible only for insurance-specific line items |
| DFY | Definity quarterly reports | Canadian P&C quarterly disclosure | Eligible for extraction fixtures |

## Non-negotiable comparability rules

- `combined_ratio`, `claims_ratio`, and `expense_ratio` require an explicitly insurance-specific Canada or Canadian P&C basis.
- TD consolidated-bank and Wealth Management totals are excluded from P&C comparisons.
- Aviva group-level values are excluded unless the source explicitly identifies its Canada segment.
- Source discovery must record a direct report URL, content hash, reporting period, and reporting basis before any KPI can be published.
