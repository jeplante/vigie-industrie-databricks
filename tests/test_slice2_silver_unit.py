from __future__ import annotations

from datetime import UTC, datetime
import inspect

from vigie_databricks.silver import classify_rejection_reason, load_silver_observations


def _valid_row() -> dict:
    return {
        "observation_id": "obs-1",
        "company_id": "C1",
        "metric_id": "revenue",
        "period_id": "2026Q2",
        "value": 123.4,
        "ingested_at": datetime.now(UTC),
    }


def test_rejection_reason_is_none_for_structurally_valid_row() -> None:
    assert classify_rejection_reason(_valid_row()) is None


def test_rejection_reason_precedence_is_first_failure() -> None:
    row = _valid_row()
    row["observation_id"] = "  "
    row["company_id"] = ""
    row["period_id"] = "BAD"
    row["value"] = None
    assert classify_rejection_reason(row) == "missing_observation_id"


def test_rejection_reason_precedence_order_is_explicit() -> None:
    row = _valid_row()
    row["company_id"] = " "
    assert classify_rejection_reason(row) == "missing_company_id"

    row = _valid_row()
    row["metric_id"] = ""
    assert classify_rejection_reason(row) == "missing_metric_id"

    row = _valid_row()
    row["period_id"] = ""
    assert classify_rejection_reason(row) == "missing_period_id"

    row = _valid_row()
    row["period_id"] = "2026-T2"
    assert classify_rejection_reason(row) == "invalid_period_id"

    row = _valid_row()
    row["value"] = float("nan")
    assert classify_rejection_reason(row) == "invalid_value"

    row = _valid_row()
    row["value"] = float("inf")
    assert classify_rejection_reason(row) == "invalid_value"

    row = _valid_row()
    row["ingested_at"] = None
    assert classify_rejection_reason(row) == "invalid_ingested_at"


def test_public_api_owns_full_snapshot_read_by_structure() -> None:
    signature = inspect.signature(load_silver_observations)
    parameters = list(signature.parameters)

    assert parameters == ["spark", "bronze_object", "silver_object"]
    assert "source_df" not in signature.parameters
