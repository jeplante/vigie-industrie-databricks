from __future__ import annotations

from apps.gold_viewer.display import display_number, display_percentage, display_value


def test_display_value_preserves_null_semantics():
    assert display_value(None) == "N/A"
    assert display_value(None, "No previous period") == "No previous period"
    assert display_value("up") == "up"


def test_display_number_is_null_safe():
    assert display_number(None) == "N/A"
    assert display_number(120) == "120.00"


def test_display_percentage_preserves_null_and_zero_semantics():
    assert display_percentage(None) == "N/A"
    assert display_percentage(0.0) == "+0.0%"
    assert display_percentage(0.2) == "+20.0%"
    assert display_percentage(-0.1) == "-10.0%"