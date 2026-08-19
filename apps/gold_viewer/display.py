from __future__ import annotations


def display_value(value: object, null_text: str = "N/A") -> str:
    return null_text if value is None else str(value)


def display_number(value: object) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.2f}"


def display_percentage(value: object) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:+,.1f}%"