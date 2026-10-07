"""Deterministic operational health checks for Finance publication, the P&C publication and the App."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
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


# Observed compute usage (2026-10; the workspace is Databricks Free Edition, so this is a usage
# quota guard, not a bill): about 1.5 DBU per day for the Jobs alone, plus 0.5 DBU per hour
# while the App runs (up to 12 per day) and SQL warehouse time when it is used, so a normal day can
# reach 15 to 20. The threshold sits above that to flag a runaway Job or cluster, not normal variation.
MAX_DAILY_DBUS = 30.0


def evaluate_usage(daily_dbus: Iterable[tuple[date, float]], today: date, max_daily_dbus: float = MAX_DAILY_DBUS) -> list[OperationsAlert]:
    """Alert when the latest complete day (yesterday) used more than ``max_daily_dbus`` DBUs of compute.

    Today is partial and ignored. A missing day is not an alert: absence of data is not heavy usage.
    """
    yesterday = today - timedelta(days=1)
    consumed = sum(float(quantity) for day, quantity in daily_dbus if day == yesterday)
    if consumed > max_daily_dbus:
        return [OperationsAlert(
            "usage_spike", "warning", "databricks",
            f"{yesterday}: consommation de calcul élevée, {consumed:.1f} DBU (seuil {max_daily_dbus:.0f}).",
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


# --- P&C -------------------------------------------------------------------------------------------------
# P&C KPIs are published only after a human review of the evidence, so a missing quarter here means
# "a report is out and the review is still to do", not a pipeline failure: these alerts are warnings.
# Expected KPIs per issuer: what each one discloses quarterly and the review has validated so far
# (Gold, 2026-10-07). Aviva Canada publishes no quarterly Canadian segment, so nothing is expected from it.
PNC_EXPECTED_METRICS: dict[str, frozenset[str]] = {
    "IFC": frozenset({"combined_ratio", "net_income", "operating_income"}),
    "DFY": frozenset({"claims_ratio", "combined_ratio", "expense_ratio", "net_income", "operating_income"}),
    "TD": frozenset({"net_income"}),
}
# Month in which each issuer's fiscal year ends; TD's ends on October 31, the others follow the calendar.
PNC_FISCAL_YEAR_END = {"TD": 10}
PNC_RATIOS = ("combined_ratio", "claims_ratio", "expense_ratio")
# Plausible range per ratio, wide around what the issuers have published since 2022 (combined 85.9-103.9 %,
# claims 59.1-74.5 %, expense 28.9-33.3 %): a value outside is far more likely an extraction or units error
# than a real quarter, while a severe catastrophe quarter still fits.
PNC_RATIO_BOUNDS = {"combined_ratio": (60.0, 150.0), "claims_ratio": (30.0, 120.0), "expense_ratio": (15.0, 50.0)}
# Claims and expense ratios add up to the combined ratio; the issuers round each to one decimal.
PNC_RATIO_TOLERANCE_PP = 0.5
QUARTER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
RESULTS_TITLE = re.compile(
    r"\b(?:reports?|announces?|posts?|releases?|delivers?)\b.*?"
    r"(?:\b(?P<word>first|second|third|fourth)[- ]quarter(?: of)?,? (?P<year>20\d\d)"
    r"|\b(?P<year2>20\d\d),? (?P<word2>first|second|third|fourth)[- ]quarter"
    r"|\bq(?P<number>[1-4])[- ]?(?P<year3>20\d\d))\b.*?\bresults\b",
    re.I,
)
FUTURE_ANNOUNCEMENT = re.compile(r"\b(?:to|will) (?:announce|release|report)\b|conference call|webcast", re.I)


def latest_completed_pnc_quarter(now: datetime, fiscal_year_end_month: int = 12,
                                 reporting_lag_days: int = REPORTING_LAG_DAYS) -> str:
    """Latest quarter of the issuer's own fiscal calendar that ended at least ``reporting_lag_days`` ago.

    Labels follow the published Gold rows: TD's quarter ending July 31, 2026 is fiscal 2026-Q3.
    """
    reference = (now - timedelta(days=reporting_lag_days)).date()
    year, month = reference.year, reference.month
    while True:
        if (month - fiscal_year_end_month) % 3 == 0 and date(year, month, calendar.monthrange(year, month)[1]) <= reference:
            quarter = (month - fiscal_year_end_month - 1) % 12 // 3 + 1
            fiscal_year = year if month <= fiscal_year_end_month else year + 1
            return f"{fiscal_year}-Q{quarter}"
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)


def announced_results_period(title: str) -> str | None:
    """"2026-Q2" for "Definity Financial Corporation Reports Second Quarter 2026 Results", else None.

    A date announcement ("to announce ... results on July 30"), a conference call or a catastrophe
    loss estimate is not a results release.
    """
    if FUTURE_ANNOUNCEMENT.search(title or ""):
        return None
    match = RESULTS_TITLE.search(title or "")
    if not match:
        return None
    word = (match.group("word") or match.group("word2") or "").lower()
    quarter = QUARTER_WORDS.get(word) or int(match.group("number"))
    return f"{match.group('year') or match.group('year2') or match.group('year3')}-Q{quarter}"


def evaluate_pnc(
    gold_rows: Iterable[dict[str, Any]],
    news_rows: Iterable[dict[str, Any]],
    *,
    now: datetime,
) -> list[OperationsAlert]:
    """Completeness of each issuer's expected quarter, plausibility of the latest ratios, and results
    announced in an official newsroom that the reviewed publication does not hold yet."""
    rows = [row for row in gold_rows if row.get("validation_status", "validated_quarterly") == "validated_quarterly"]
    alerts: list[OperationsAlert] = []
    for company, expected_metrics in PNC_EXPECTED_METRICS.items():
        period = latest_completed_pnc_quarter(now, PNC_FISCAL_YEAR_END.get(company, 12))
        published = {str(row.get("metric_id")) for row in rows if row.get("company_id") == company and row.get("period_id") == period}
        missing = sorted(expected_metrics - published)
        if missing:
            alerts.append(OperationsAlert(
                "pnc_quarter_incomplete", "warning", company,
                f"{period}: KPI P&C non publiés: {', '.join(missing)}. Revue des preuves à faire avant publication.",
            ))
    latest_by_company: dict[str, str] = {}
    for row in rows:
        company, period = str(row.get("company_id") or ""), str(row.get("period_id") or "")
        if re.fullmatch(r"20\d\d-Q[1-4]", period) and period > latest_by_company.get(company, ""):
            latest_by_company[company] = period
    for company, period in sorted(latest_by_company.items()):
        values = {str(row.get("metric_id")): float(row["value"]) for row in rows
                  if row.get("company_id") == company and row.get("period_id") == period and row.get("value") is not None}
        for metric in PNC_RATIOS:
            low, high = PNC_RATIO_BOUNDS[metric]
            if metric in values and not low <= values[metric] <= high:
                alerts.append(OperationsAlert(
                    "pnc_value_anomalous", "critical", company,
                    f"{period} {metric}: {values[metric]:.1f} % hors de l'intervalle plausible {low:.0f}-{high:.0f} %.",
                ))
        if all(metric in values for metric in PNC_RATIOS):
            gap = values["claims_ratio"] + values["expense_ratio"] - values["combined_ratio"]
            if abs(gap) > PNC_RATIO_TOLERANCE_PP:
                alerts.append(OperationsAlert(
                    "pnc_value_anomalous", "critical", company,
                    f"{period}: sinistres + frais ({values['claims_ratio'] + values['expense_ratio']:.1f} %) "
                    f"ne donnent pas le ratio combiné ({values['combined_ratio']:.1f} %).",
                ))
    announced: dict[str, tuple[str, Any]] = {}
    for article in news_rows:
        company = str(article.get("company_id") or "")
        period = announced_results_period(str(article.get("title") or ""))
        if company in PNC_EXPECTED_METRICS and period and period > announced.get(company, ("", None))[0]:
            announced[company] = (period, article.get("published_at"))
    for company, (period, published_at) in sorted(announced.items()):
        if period > latest_by_company.get(company, ""):
            day = published_at.strftime("%Y-%m-%d") if hasattr(published_at, "strftime") else str(published_at or "")[:10]
            alerts.append(OperationsAlert(
                "pnc_results_announced", "warning", company,
                f"Résultats {period} annoncés le {day}; KPI non publiés. Revue des preuves à faire avant publication.",
            ))
    return alerts
