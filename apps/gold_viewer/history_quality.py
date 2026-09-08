"""Non-destructive quality flags for chart display."""
from __future__ import annotations

from statistics import median
from typing import Any

ADDITIVE_METRICS = {"core_earnings", "net_income", "new_business_value", "ape_sales"}


def flag_suspicious_history(rows: list[dict[str, Any]], metric_id: str) -> list[dict[str, Any]]:
    """Flag isolated annual-looking spikes without changing published observations.

    A point is hidden only when it is at least 2.5x the median of its immediate
    neighbours for an additive metric. It remains available in the source data.
    """
    ordered = sorted((dict(row) for row in rows), key=lambda row: (row["company_id"], row["period_id"]))
    if metric_id not in ADDITIVE_METRICS:
        return [row | {"display_quality": "accepted"} for row in ordered]
    by_company: dict[str, list[dict[str, Any]]] = {}
    for row in ordered:
        by_company.setdefault(row["company_id"], []).append(row)
    flagged: list[dict[str, Any]] = []
    for series in by_company.values():
        for index, row in enumerate(series):
            neighbours = [float(series[i]["value"]) for i in (index - 1, index + 1) if 0 <= i < len(series) and series[i].get("value") not in (None, 0)]
            value = row.get("value")
            baseline = median(neighbours) if neighbours else None
            suspicious = value not in (None, 0) and baseline not in (None, 0) and abs(float(value)) >= 2.5 * abs(float(baseline))
            flagged.append(row | {"display_quality": "suspect_annual_like" if suspicious else "accepted", "display_value": None if suspicious else value})
    return sorted(flagged, key=lambda row: (row["period_id"], row["company_id"]))
