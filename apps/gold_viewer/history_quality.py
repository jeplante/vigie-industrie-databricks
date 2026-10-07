"""Non-destructive quality flags for chart display."""
from __future__ import annotations

import math
from statistics import median
from typing import Any

ADDITIVE_METRICS = {"core_earnings", "net_income", "new_business_value", "ape_sales"}


def flag_suspicious_history(rows: list[dict[str, Any]], metric_id: str, additive_metrics=ADDITIVE_METRICS) -> list[dict[str, Any]]:
    """Flag isolated annual-looking spikes without changing published observations.

    A point is hidden only when it has two usable immediate neighbours and is
    at least 2.5x their median for an additive metric. It remains available in
    the source data. ``additive_metrics`` names the flow metrics of the universe
    being drawn (life by default).
    """
    ordered = sorted((dict(row) for row in rows), key=lambda row: (row["company_id"], row["period_id"]))
    if metric_id not in additive_metrics:
        return [row | {"display_quality": "accepted", "display_value": row.get("value")} for row in ordered]
    by_company: dict[str, list[dict[str, Any]]] = {}
    for row in ordered:
        by_company.setdefault(row["company_id"], []).append(row)
    flagged: list[dict[str, Any]] = []
    for series in by_company.values():
        for index, row in enumerate(series):
            neighbours = [float(series[i]["value"]) for i in (index - 1, index + 1) if 0 <= i < len(series) and series[i].get("value") not in (None, 0)]
            value = row.get("value")
            baseline = median(neighbours) if neighbours else None
            suspicious = len(neighbours) == 2 and value not in (None, 0) and baseline not in (None, 0) and abs(float(value)) >= 2.5 * abs(float(baseline))
            flagged.append(row | {"display_quality": "suspect_annual_like" if suspicious else "accepted", "display_value": None if suspicious else value})
    return sorted(flagged, key=lambda row: (row["period_id"], row["company_id"]))


def year_to_date_values(rows: list[dict[str, Any]]) -> list[float | None]:
    """Cumulate quarterly values per company and year, aligned with ``rows``.

    A year-to-date value is shown only while every quarter since Q1 has a
    displayable value; after a missing or masked quarter it stays ``None``
    instead of silently understating the cumulative total.
    """
    totals: dict[tuple[str, str], tuple[int, float | None]] = {}
    ordered = sorted(range(len(rows)), key=lambda index: (rows[index]["company_id"], rows[index]["period_id"]))
    values: list[float | None] = [None] * len(rows)
    for index in ordered:
        row = rows[index]
        period = str(row["period_id"])
        key = (row["company_id"], period[:4])
        quarter = int(period[-1])
        previous_quarter, running = totals.get(key, (0, 0.0))
        value = row.get("display_value")
        usable = value is not None and not (isinstance(value, float) and math.isnan(value))
        if running is None or not usable or quarter != previous_quarter + 1:
            running = None
        else:
            running += float(value)
        totals[key] = (quarter, running)
        values[index] = running
    return values
