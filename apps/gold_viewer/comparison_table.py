"""Presentation-only renderer for the published insurer comparison."""
from __future__ import annotations

import re
from typing import Any

from shared_ui import (
    BRAND,
    delta_badge,
    empty_cell,
    format_value,
    header_cell,
    row_header_cell,
    row_open,
    table_shell,
    value_cell,
)

# Life-universe view of the shared brand registry (name, colour), kept as a
# module constant for backward compatibility with existing imports and tests.
COMPANIES = {company_id: BRAND[company_id] for company_id in ("MFC", "SLF", "GWO", "IAG")}
METRICS = (
    ("core_eps", "BPA activités de base", "per_share"),
    ("core_earnings", "Résultat des activités de base", "billion"),
    ("net_income", "Résultat net", "billion"),
    (("licat_ratio", "solvency_ratio"), "Ratio LICAT / solvabilité", "percent"),
    (("assets_under_management", "assets_under_administration", "total_client_assets"), "Actifs gérés / administrés", "assets"),
    ("core_roe", "Rendement des capitaux propres de base", "percent"),
)
HELP = {
    "BPA activités de base": "Bénéfice de base par action, en dollars canadiens.",
    "Résultat des activités de base": "Résultat des activités de base, en milliards de dollars canadiens.",
    "Résultat net": "Résultat net attribuable aux actionnaires, en milliards de dollars canadiens.",
    "Ratio LICAT / solvabilité": "Ratio de capital ou de solvabilité déclaré par l’assureur, en pourcentage.",
    "Actifs gérés / administrés": "Mesure d’actifs propre à chaque assureur : gestion, administration ou actifs clients.",
    "Rendement des capitaux propres de base": "Rendement des capitaux propres de base, en pourcentage.",
}

QUARTER_PATTERN = re.compile(r"^(?P<year>20[0-9]{2})-Q(?P<quarter>[1-4])$")


def latest_quarter_period(
    all_rows: dict[str, list[dict[str, Any]]],
    additional_periods: list[str] | None = None,
) -> str | None:
    """Return one explicit latest quarterly period; annual periods never qualify."""
    periods = {
        str(row.get("current_period_id"))
        for rows in all_rows.values()
        for row in rows
        if QUARTER_PATTERN.fullmatch(str(row.get("current_period_id") or ""))
    }
    periods.update(
        period for period in (additional_periods or []) if QUARTER_PATTERN.fullmatch(str(period))
    )
    return max(periods) if periods else None


def rows_for_period(
    all_rows: dict[str, list[dict[str, Any]]], period_id: str | None
) -> dict[str, list[dict[str, Any]]]:
    """Do not substitute an older KPI when the target-quarter value is absent."""
    return {
        company: [row for row in rows if row.get("current_period_id") == period_id]
        for company, rows in all_rows.items()
    }


def expected_yoy_period(period_id: str | None) -> str | None:
    match = QUARTER_PATTERN.fullmatch(str(period_id or ""))
    if not match:
        return None
    return f"{int(match['year']) - 1}-Q{match['quarter']}"


def _metric_row(rows: list[dict[str, Any]], selector: str | tuple[str, ...]) -> dict[str, Any] | None:
    metric_ids = (selector,) if isinstance(selector, str) else selector
    return next((row for metric_id in metric_ids for row in rows if row.get("metric_id") == metric_id), None)


def _delta(row: dict[str, Any], kind: str) -> tuple[str, str, str]:
    expected_period = expected_yoy_period(row.get("current_period_id"))
    if not expected_period or row.get("previous_period_id") != expected_period:
        return "N/A", "flat", f"vs {expected_period}" if expected_period else ""
    direction = row.get("direction")
    if not direction: return "N/A", "flat", f"vs {expected_period}"
    change = row.get("change_value") if kind == "percent" else row.get("change_pct")
    if change is None: return "N/A", "flat", f"vs {expected_period}"
    text = f"{float(change):+.1f} pp" if kind == "percent" else f"{float(change) * 100:+.1f} %"
    symbol = "▲" if direction == "up" else "▼" if direction == "down" else "•"
    tone = "up" if direction == "up" else "down" if direction == "down" else "flat"
    previous_period = row.get("previous_period_id")
    return f"{symbol} {text}", tone, f"vs {previous_period}" if previous_period else ""


def comparison_html(all_rows: dict[str, list[dict[str, Any]]]) -> str:
    """Render an accessible, compact table from already published rows."""
    header_cells = [header_cell("Compagnie")]
    header_cells += [header_cell(label, HELP[label]) for _, label, _ in METRICS]
    body: list[str] = []
    for company_id in ("MFC", "SLF", "GWO", "IAG"):
        rows = all_rows.get(company_id, [])
        period = next((row.get("current_period_id") for row in rows if row.get("current_period_id")), None)
        ticker = f"{company_id}.{period}" if period else company_id
        cells: list[str] = [row_header_cell(company_id, ticker)]
        for selector, _, kind in METRICS:
            row = _metric_row(rows, selector)
            if not row:
                cells.append(empty_cell())
                continue
            delta, tone, delta_period = _delta(row, kind)
            value = format_value(row.get("current_value"), kind, row.get("metric_id", ""))
            cells.append(value_cell(
                value,
                period=row.get("current_period_id"),
                delta_html=delta_badge(delta, tone, delta_period) if delta else "",
            ))
        body.append(row_open(company_id) + "".join(cells) + "</tr>")
    return table_shell(header_cells, body)
