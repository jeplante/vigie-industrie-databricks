from apps.gold_viewer.comparison_table import comparison_html


def test_comparison_table_renders_value_period_delta_and_empty_cell():
    html = comparison_html({"MFC": [{"metric_id": "core_eps", "current_period_id": "2026-Q2", "previous_period_id": "2026-Q1", "current_value": 1.09, "change_pct": 0.147, "direction": "up"}], "SLF": [], "GWO": [], "IAG": []})
    assert "Manuvie" in html
    assert "1.09 $" in html
    assert "2026-Q2" in html
    assert "▲ +14.7 %" in html
    assert "vs 2026-Q1" in html
    assert "comparison-empty" in html
    assert "Bénéfice de base par action" in html


def test_comparison_table_uses_asset_and_solvency_metric_variants():
    html = comparison_html({"IAG": [{"metric_id": "solvency_ratio", "current_period_id": "2026-Q2", "current_value": 137, "change_value": -1, "direction": "down"}, {"metric_id": "assets_under_administration", "current_period_id": "2026-Q2", "current_value": 374, "change_pct": 0.36, "direction": "up"}], "MFC": [], "SLF": [], "GWO": []})
    assert "137.0 %" in html
    assert "▼ -1.0 pp" in html
    assert "374 G$" in html
