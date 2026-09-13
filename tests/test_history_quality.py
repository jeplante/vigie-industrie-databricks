from apps.gold_viewer.history_quality import flag_suspicious_history


def test_hides_isolated_annual_looking_additive_spike_without_mutating_value():
    rows = [
        {"company_id": "MFC", "period_id": "2023-Q3", "value": 1.7},
        {"company_id": "MFC", "period_id": "2023-Q4", "value": 5.3},
        {"company_id": "MFC", "period_id": "2024-Q1", "value": 1.8},
    ]
    quality = flag_suspicious_history(rows, "core_earnings")
    spike = next(row for row in quality if row["period_id"] == "2023-Q4")
    assert spike["display_quality"] == "suspect_annual_like"
    assert spike["value"] == 5.3
    assert spike["display_value"] is None


def test_keeps_point_in_time_metrics_visible():
    quality = flag_suspicious_history([
        {"company_id": "MFC", "period_id": "2023-Q3", "value": 130},
        {"company_id": "MFC", "period_id": "2023-Q4", "value": 150},
    ], "licat_ratio")
    assert all(row["display_quality"] == "accepted" for row in quality)
