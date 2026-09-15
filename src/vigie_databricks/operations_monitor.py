"""Deterministic operational health checks for Finance publication and the App."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from vigie_databricks.finance_extraction import EXPECTED_METRICS


@dataclass(frozen=True)
class OperationsAlert:
    alert_type: str
    severity: str
    entity: str
    message: str


def latest_completed_quarter(now: datetime) -> str:
    """Return the latest fully completed calendar quarter."""
    year = now.year
    current_quarter = (now.month - 1) // 3 + 1
    if current_quarter == 1:
        return f"{year - 1}-Q4"
    return f"{year}-Q{current_quarter - 1}"


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
