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


def test_keeps_two_point_additive_history_visible():
    rows = [
        {"company_id": "MFC", "period_id": "2025-Q4", "value": 1.0},
        {"company_id": "MFC", "period_id": "2026-Q1", "value": 3.0},
    ]

    quality = flag_suspicious_history(rows, "core_earnings")

    assert [row["display_quality"] for row in quality] == ["accepted", "accepted"]
    assert [row["display_value"] for row in quality] == [1.0, 3.0]
    assert rows == [
        {"company_id": "MFC", "period_id": "2025-Q4", "value": 1.0},
        {"company_id": "MFC", "period_id": "2026-Q1", "value": 3.0},
    ]


def test_point_in_time_metrics_expose_their_value_for_display():
    quality = flag_suspicious_history([{"company_id": "MFC", "period_id": "2023-Q3", "value": 130}], "licat_ratio")
    assert quality[0]["display_value"] == 130


def test_year_to_date_is_missing_after_an_absent_or_masked_quarter():
    from apps.gold_viewer.history_quality import year_to_date_values

    rows = [
        {"company_id": "MFC", "period_id": "2025-Q2", "display_value": 2.0},
        {"company_id": "MFC", "period_id": "2025-Q1", "display_value": 1.0},
        {"company_id": "MFC", "period_id": "2025-Q3", "display_value": float("nan")},
        {"company_id": "MFC", "period_id": "2025-Q4", "display_value": 4.0},
        {"company_id": "SLF", "period_id": "2025-Q2", "display_value": 5.0},
        {"company_id": "MFC", "period_id": "2026-Q1", "display_value": 3.0},
    ]
    assert year_to_date_values(rows) == [3.0, 1.0, None, None, None, 3.0]
