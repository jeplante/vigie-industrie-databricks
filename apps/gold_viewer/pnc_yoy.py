"""Year-over-year change of a published P&C observation, only when the comparison is legitimate.

Shared by the page badges and the chat so both apply the same guardrails: the same issuer and metric,
the same quarter one year earlier, and the same calendar basis (a fiscal quarter is never compared with a
calendar one). Anything else is not a comparison.
"""
from __future__ import annotations

from typing import Any

# Direction in which a change is favourable, mirrored from config/pnc/metrics.yaml (a test keeps them equal):
# amounts are better higher, ratios better lower.
FAVORABLE_TREND = {
    "insurance_revenue": "up", "combined_ratio": "down", "claims_ratio": "down", "expense_ratio": "down",
    "catastrophe_losses": "down", "operating_income": "up", "net_income": "up", "operating_roe": "up",
}


def kind_of(row: dict[str, Any]) -> str:
    """Billions for CAD amounts, percent for ratios — drives the shared formatter."""
    return "billion" if row.get("unit") == "CAD_BILLION" else "percent"


def prior_year_period(period_id: str) -> str | None:
    if len(period_id) == 7 and period_id[4:6] == "-Q":
        return f"{int(period_id[:4]) - 1}{period_id[4:]}"
    return None


def prior_year_row(current_row: dict[str, Any], all_rows) -> dict[str, Any] | None:
    prior_period = prior_year_period(str(current_row.get("period_id", "")))
    if not prior_period:
        return None
    return next(
        (row for row in all_rows
         if row.get("company_id") == current_row.get("company_id")
         and row.get("metric_id") == current_row.get("metric_id")
         and row.get("period_id") == prior_period
         and row.get("calendar_basis") == current_row.get("calendar_basis")),
        None,
    )


def pnc_yoy(current_row: dict[str, Any], all_rows) -> tuple[str, str, str] | None:
    """(change text, direction symbol, prior period) only when the comparison is legitimate, else None."""
    prior = prior_year_row(current_row, all_rows)
    if prior is None or prior.get("value") is None or current_row.get("value") is None:
        return None
    current_value = float(current_row["value"])
    prior_value = float(prior["value"])
    if kind_of(current_row) == "percent":
        change = current_value - prior_value
        text = f"{change:+.1f} pp"
    else:
        if prior_value == 0:
            return None
        change = (current_value - prior_value) / prior_value * 100
        text = f"{change:+.1f} %"
    symbol = "▲" if change > 0 else "▼" if change < 0 else "•"
    return text, symbol, prior["period_id"]


def favourability(metric_id: str, symbol: str) -> str:
    """"up" when the change is favourable for this metric, "down" when unfavourable, "flat" otherwise.

    The returned word is the badge tone of the shared table (green, red, grey), the same colours the
    life table uses; the arrow in the badge still shows the actual direction of the value.
    """
    trend = FAVORABLE_TREND.get(metric_id)
    if trend is None or symbol not in ("▲", "▼"):
        return "flat"
    return "up" if (symbol == "▲") == (trend == "up") else "down"
