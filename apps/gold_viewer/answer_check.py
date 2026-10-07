"""Cross-check the figures a model wrote against the figures it was given.

The chat guardrails already drop citations and KPIs that are not in the context. This adds a check on
the numbers in the prose: a figure followed by a unit (%, pp, $, millions, milliards...) must be traceable
to a value of the context, to a unit conversion of it, or to a difference or percentage change between
two values of the same series. It catches invented numbers; it cannot tell that a real number was
attached to the wrong label, so a pass is not a proof of correctness.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

UNIT = r"(?:%|pp\b|\$|G\$|M\$|T\$|millions?\b|milliards?\b|billions?\b|mds\b|M\b|B\b)"
FIGURE = re.compile(rf"(?<![\w.,])([-+]?\d+(?:[   ]\d{{3}})*(?:[.,]\d+)?)\s*({UNIT})", re.IGNORECASE)
# Unit conversions between what the context stores (billions, fractions) and what a sentence may say.
SCALES = (1, 100, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9)


def _leaves(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _leaves(item)


def _series(context: Any) -> list[list[float]]:
    """Values of one (company, metric) across periods: the differences between them are legitimate figures."""
    rows: list[dict[str, Any]] = []
    if isinstance(context, dict):
        for key in ("observations", "comparisons"):
            rows += [row for row in context.get(key, []) if isinstance(row, dict)]
    grouped: dict[tuple[Any, Any], list[float]] = {}
    for row in rows:
        for field in ("value", "current_value", "previous_value"):
            if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool):
                grouped.setdefault((row.get("company_id"), row.get("metric_id")), []).append(float(row[field]))
    return list(grouped.values())


def allowed_figures(context: Any) -> list[float]:
    values = set(_leaves(context))
    for series in _series(context):
        for first in series:
            for second in series:
                if first != second:
                    values.add(first - second)
                    if second:
                        values.add((first - second) / abs(second) * 100)
    return sorted(values)


def _parse(raw: str) -> tuple[float, int]:
    cleaned = re.sub(r"[   ]", "", raw).replace(",", ".")
    decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
    return abs(float(cleaned)), decimals


def unsupported_figures(text: str, context: Any) -> list[str]:
    """Figures with a unit in ``text`` that no value of ``context`` explains (empty list = all traced)."""
    allowed = [abs(value) for value in allowed_figures(context)]
    unsupported = []
    for match in FIGURE.finditer(text or ""):
        number, decimals = _parse(match.group(1))
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(candidate * scale - number) <= tolerance for candidate in allowed for scale in SCALES):
            unsupported.append(match.group(0).strip())
    return list(dict.fromkeys(unsupported))
