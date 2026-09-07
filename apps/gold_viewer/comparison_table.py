"""Presentation-only renderer for the published insurer comparison."""
from __future__ import annotations

from html import escape
from typing import Any

COMPANIES = {"MFC": ("Manuvie", "#1677c8"), "SLF": ("Sun Life", "#f4b400"), "GWO": ("Great-West Lifeco", "#d99800"), "IAG": ("iA Groupe financier", "#c54b8c")}
METRICS = (
    ("core_eps", "BPA activités de base", "per_share"),
    ("core_earnings", "Résultat des activités de base", "billion"),
    ("net_income", "Résultat net", "billion"),
    (("licat_ratio", "solvency_ratio"), "Ratio LICAT / solvabilité", "percent"),
    (("assets_under_management", "assets_under_administration", "total_client_assets"), "Actifs gérés / administrés", "assets"),
    ("core_roe", "Rendement des capitaux propres de base", "percent"),
)


def _format_value(value: Any, kind: str, metric_id: str) -> str:
    if value is None:
        return "—"
    number = float(value)
    if kind == "per_share": return f"{number:,.2f} $"
    if kind == "billion": return f"{number:,.3f} G$"
    if kind == "assets": return f"{number:,.1f} T$" if metric_id == "total_client_assets" else f"{number:,.0f} G$"
    return f"{number:.1f} %"


def _metric_row(rows: list[dict[str, Any]], selector: str | tuple[str, ...]) -> dict[str, Any] | None:
    metric_ids = (selector,) if isinstance(selector, str) else selector
    return next((row for metric_id in metric_ids for row in rows if row.get("metric_id") == metric_id), None)


def _delta(row: dict[str, Any], kind: str) -> tuple[str, str]:
    direction = row.get("direction")
    if not direction: return "", ""
    change = row.get("change_value") if kind == "percent" else row.get("change_pct")
    if change is None: return "", ""
    text = f"{float(change):+.1f} pp" if kind == "percent" else f"{float(change) * 100:+.1f} %"
    symbol = "▲" if direction == "up" else "▼" if direction == "down" else "•"
    tone = "up" if direction == "up" else "down" if direction == "down" else "flat"
    return f"{symbol} {text}", tone


def comparison_html(all_rows: dict[str, list[dict[str, Any]]]) -> str:
    """Render an accessible, compact table from already published rows."""
    header = "".join(f"<th scope='col'>{escape(label)}</th>" for _, label, _ in METRICS)
    body: list[str] = []
    for company_id in ("MFC", "SLF", "GWO", "IAG"):
        rows = all_rows.get(company_id, [])
        name, colour = COMPANIES[company_id]
        period = next((row.get("current_period_id") for row in rows if row.get("current_period_id")), None)
        cells: list[str] = []
        for selector, _, kind in METRICS:
            row = _metric_row(rows, selector)
            if not row:
                cells.append("<td class='comparison-empty'>—</td>")
                continue
            delta, tone = _delta(row, kind)
            value = _format_value(row.get("current_value"), kind, row.get("metric_id", ""))
            cells.append("<td><strong>" + escape(value) + "</strong>" + (f"<span class='comparison-period'>{escape(str(row.get('current_period_id') or ''))}</span>" if row.get("current_period_id") else "") + (f"<span class='comparison-delta {tone}'>{escape(delta)}</span>" if delta else "") + "</td>")
        body.append(f"<tr style='--company-colour:{escape(colour)}'><th scope='row'><strong>{escape(name)}</strong><span class='comparison-ticker'>{escape(company_id)}{'.' + escape(str(period)) if period else ''}</span></th>" + "".join(cells) + "</tr>")
    return "<div class='comparison-wrap'><table class='comparison-table'><thead><tr><th scope='col'>Compagnie</th>" + header + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
