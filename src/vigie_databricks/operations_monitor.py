"""Deterministic operational health checks for Finance publication and the App."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from vigie_databricks.finance_extraction import EXPECTED_METRICS


@dataclass(frozen=True)
class OperationsAlert:
    alert_type: str
    severity: str
    entity: str
    message: str


# Insurers publish a quarter roughly five to seven weeks after it ends (Q4 is the
# latest, mid-February). Expecting a quarter's KPIs before then raised a daily
# critical alert for every company during the reporting window.
REPORTING_LAG_DAYS = 50


def latest_completed_quarter(now: datetime, reporting_lag_days: int = REPORTING_LAG_DAYS) -> str:
    """Return the latest calendar quarter that ended at least ``reporting_lag_days`` ago."""
    reference = now - timedelta(days=reporting_lag_days)
    current_quarter = (reference.month - 1) // 3 + 1
    if current_quarter == 1:
        return f"{reference.year - 1}-Q4"
    return f"{reference.year}-Q{current_quarter - 1}"


# Observed consumption (2026-10): about 1.5 DBU per day for the Jobs alone, plus 0.5 DBU per hour
# while the App runs (up to 12 per day) and SQL warehouse time when it is used, so a normal day can
# reach 15 to 20. The threshold sits above that to flag a runaway Job or cluster, not normal variation.
MAX_DAILY_DBUS = 30.0


def evaluate_cost(daily_dbus: Iterable[tuple[date, float]], today: date, max_daily_dbus: float = MAX_DAILY_DBUS) -> list[OperationsAlert]:
    """Alert when the latest complete day (yesterday) consumed more than ``max_daily_dbus`` DBUs.

    Today is partial and ignored. A missing day is not an alert: absence of data is not overspending.
    """
    yesterday = today - timedelta(days=1)
    consumed = sum(float(quantity) for day, quantity in daily_dbus if day == yesterday)
    if consumed > max_daily_dbus:
        return [OperationsAlert(
            "cost_spike", "warning", "databricks",
            f"{yesterday}: {consumed:.1f} DBU consommées (seuil {max_daily_dbus:.0f}).",
        )]
    return []


def evaluate_operations(
    gold_rows: Iterable[dict[str, Any]],
    finance_audit: dict[str, Any] | None,
    rejected_current: Iterable[dict[str, Any]],
    *,
    expected_period: str,
    app_state: str,
    compute_state: str,
) -> list[OperationsAlert]:
    """Return actionable alerts; an empty list means all monitored controls passed."""
    alerts: list[OperationsAlert] = []
    if not finance_audit or finance_audit.get("quality_status") != "current":
        alerts.append(OperationsAlert("publication_failure", "critical", "finance", "La dernière publication Finance n'est pas current."))
    if not finance_audit or int(finance_audit.get("sources_succeeded") or 0) != 4 or int(finance_audit.get("sources_failed") or 0) != 0:
        alerts.append(OperationsAlert("source_missing", "critical", "finance", "Les quatre sources Finance n'ont pas toutes réussi."))

    observed: dict[str, set[str]] = {company: set() for company in EXPECTED_METRICS}
    for row in gold_rows:
        company = str(row.get("company_id") or "")
        if company in observed and row.get("current_period_id") == expected_period:
            observed[company].add(str(row.get("metric_id") or ""))
    for company, metrics in observed.items():
        missing = sorted(EXPECTED_METRICS[company] - metrics)
        if missing:
            alerts.append(OperationsAlert(
                "current_quarter_incomplete", "critical", company,
                f"{expected_period}: KPI manquants: {', '.join(missing)}.",
            ))

    for row in rejected_current:
        alerts.append(OperationsAlert(
            "current_value_anomalous", "critical", str(row.get("company_id") or "finance"),
            f"{row.get('period_id')} {row.get('metric_id')}: {row.get('validation_reason') or 'valeur rejetée'}.",
        ))
    if app_state != "RUNNING" or compute_state != "ACTIVE":
        alerts.append(OperationsAlert(
            "app_unavailable", "critical", "vigie-gold-viewer",
            f"App={app_state or 'UNKNOWN'}, compute={compute_state or 'UNKNOWN'}.",
        ))
    return alerts
