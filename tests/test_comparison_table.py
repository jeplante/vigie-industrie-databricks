from apps.gold_viewer.comparison_table import comparison_html, expected_yoy_period, latest_quarter_period, rows_for_period


def test_comparison_table_renders_value_period_delta_and_empty_cell():
    html = comparison_html({"MFC": [{"metric_id": "core_eps", "current_period_id": "2026-Q2", "previous_period_id": "2025-Q2", "current_value": 1.09, "change_pct": 0.147, "direction": "up"}], "SLF": [], "GWO": [], "IAG": []})
    assert "Manuvie" in html
    assert "1.09 $" in html
    assert "2026-Q2" in html
    assert "▲ +14.7 %" in html
    assert "vs 2025-Q2" in html
    assert "comparison-empty" in html
    assert "N/A" in html
    assert "Bénéfice de base par action" in html


def test_comparison_table_uses_asset_and_solvency_metric_variants():
    html = comparison_html({"IAG": [{"metric_id": "solvency_ratio", "current_period_id": "2026-Q2", "previous_period_id": "2025-Q2", "current_value": 137, "change_value": -1, "direction": "down"}, {"metric_id": "assets_under_administration", "current_period_id": "2026-Q2", "previous_period_id": "2025-Q2", "current_value": 374, "change_pct": 0.36, "direction": "up"}], "MFC": [], "SLF": [], "GWO": []})
    assert "137.0 %" in html
    assert "▼ -1.0 pp" in html
    assert "374 G$" in html


def test_latest_quarter_excludes_annual_and_period_filter_does_not_backfill():
    rows = {
        "MFC": [{"metric_id": "core_eps", "current_period_id": "2026-Q2"}],
        "IAG": [{"metric_id": "assets_under_management", "current_period_id": "2026-AN"}],
        "GWO": [{"metric_id": "core_earnings", "current_period_id": "2023-Q1"}],
    }
    assert latest_quarter_period(rows, ["2026-Q1"]) == "2026-Q2"
    filtered = rows_for_period(rows, "2026-Q2")
    assert filtered["MFC"]
    assert filtered["IAG"] == []
    assert filtered["GWO"] == []
    assert expected_yoy_period("2026-Q2") == "2025-Q2"


def test_delta_is_suppressed_when_previous_available_period_is_not_yoy():
    html = comparison_html({"MFC": [{"metric_id": "core_eps", "current_period_id": "2026-Q2", "previous_period_id": "2025-Q4", "current_value": 1.09, "change_pct": -0.74, "direction": "down"}]})
    assert "▼ -74.0 %" not in html
    assert "N/A" in html
    assert "vs 2025-Q2" in html
