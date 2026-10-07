from datetime import UTC, datetime

from vigie_databricks.finance_extraction import EXPECTED_METRICS
from vigie_databricks.operations_monitor import evaluate_operations, latest_completed_quarter


def healthy_rows(period="2026-Q2"):
    return [
        {"company_id": company, "metric_id": metric, "current_period_id": period}
        for company, metrics in EXPECTED_METRICS.items()
        for metric in metrics
    ]


def test_latest_completed_quarter_handles_year_boundary():
    assert latest_completed_quarter(datetime(2026, 9, 15, tzinfo=UTC)) == "2026-Q2"
    assert latest_completed_quarter(datetime(2026, 3, 20, tzinfo=UTC)) == "2025-Q4"


def test_quarter_is_not_expected_during_the_reporting_window():
    # Q3 ended 2026-09-30; insurers publish in November, so early October must still expect Q2.
    assert latest_completed_quarter(datetime(2026, 10, 1, tzinfo=UTC)) == "2026-Q2"
    assert latest_completed_quarter(datetime(2026, 10, 6, tzinfo=UTC)) == "2026-Q2"
    assert latest_completed_quarter(datetime(2026, 11, 18, tzinfo=UTC)) == "2026-Q2"
    assert latest_completed_quarter(datetime(2026, 11, 20, tzinfo=UTC)) == "2026-Q3"


def test_q4_is_expected_only_after_the_mid_february_reporting_window():
    assert latest_completed_quarter(datetime(2027, 1, 3, tzinfo=UTC)) == "2026-Q3"
    assert latest_completed_quarter(datetime(2027, 2, 18, tzinfo=UTC)) == "2026-Q3"
    assert latest_completed_quarter(datetime(2027, 2, 21, tzinfo=UTC)) == "2026-Q4"


def test_reporting_lag_is_configurable():
    assert latest_completed_quarter(datetime(2026, 10, 6, tzinfo=UTC), reporting_lag_days=0) == "2026-Q3"


def test_healthy_operations_have_no_alerts():
    alerts = evaluate_operations(
        healthy_rows(), {"quality_status": "current", "sources_succeeded": 4, "sources_failed": 0}, [],
        expected_period="2026-Q2", app_state="RUNNING", compute_state="ACTIVE",
    )
    assert alerts == []


def test_monitor_reports_source_kpi_anomaly_and_app_failures():
    rows = healthy_rows()
    rows.pop()
    alerts = evaluate_operations(
        rows, {"quality_status": "stale", "sources_succeeded": 3, "sources_failed": 1},
        [{"company_id": "GWO", "period_id": "2026-Q2", "metric_id": "core_eps", "validation_reason": "extreme"}],
        expected_period="2026-Q2", app_state="UNAVAILABLE", compute_state="STOPPED",
    )
    kinds = {alert.alert_type for alert in alerts}
    assert kinds == {"publication_failure", "source_missing", "current_quarter_incomplete", "current_value_anomalous", "app_unavailable"}
