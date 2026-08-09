from __future__ import annotations

import inspect

import pytest


def compute_change_pct(current: float, previous: float | None) -> float | None:
    if previous is None:
        return None
    if previous != 0:
        return (current - previous) / abs(previous)
    if current == 0:
        return 0.0
    return None


def test_change_pct_semantics() -> None:
    assert compute_change_pct(10.0, 5.0) == 1.0
    assert compute_change_pct(0.0, 0.0) == 0.0
    assert compute_change_pct(5.0, 0.0) is None


def test_gold_public_api_owns_full_snapshot_read_by_structure() -> None:
    from vigie_databricks.gold import load_gold_observations

    signature = inspect.signature(load_gold_observations)
    parameters = list(signature.parameters)

    assert parameters == ["spark", "silver_object", "gold_object"]
    assert "source_df" not in signature.parameters
