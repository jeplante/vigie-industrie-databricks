from __future__ import annotations

import os

import pytest

from apps.gold_viewer.gold_data import GoldConfig, fetch_companies, fetch_company_metrics, fetch_comparison


class FakeCursor:
    def __init__(self, rows, columns):
        self.rows = rows
        self.description = [(column,) for column in columns]
        self.statement = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=()):
        self.statement = statement
        self.parameters = parameters

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows, columns):
        self.cursor_instance = FakeCursor(rows, columns)

    def cursor(self):
        return self.cursor_instance


def config() -> GoldConfig:
    return GoldConfig("workspace", "default", "vigie_slice4_gold")


def test_gold_config_reads_external_identifiers(monkeypatch):
    monkeypatch.setenv("GOLD_CATALOG", "workspace")
    monkeypatch.setenv("GOLD_SCHEMA", "default")
    monkeypatch.setenv("GOLD_TABLE", "vigie_slice4_gold")

    assert GoldConfig.from_environment().qualified_table == "`workspace`.`default`.`vigie_slice4_gold`"


def test_gold_config_rejects_untrusted_identifier(monkeypatch):
    monkeypatch.setenv("GOLD_CATALOG", "workspace")
    monkeypatch.setenv("GOLD_SCHEMA", "default")
    monkeypatch.setenv("GOLD_TABLE", "gold; DROP TABLE other")

    with pytest.raises(ValueError, match="Invalid trusted Gold identifier"):
        GoldConfig.from_environment()


def test_fetch_companies_is_read_only_and_deterministic():
    connection = FakeConnection([("C1",), ("C2",)], ["company_id"])

    assert fetch_companies(connection, config()) == ["C1", "C2"]
    assert connection.cursor_instance.parameters == ()
    assert connection.cursor_instance.statement.lstrip().startswith("SELECT")


def test_fetch_company_metrics_binds_company_id():
    connection = FakeConnection([("margin",), ("revenue",)], ["metric_id"])

    assert fetch_company_metrics(connection, config(), "C1") == ["margin", "revenue"]
    assert connection.cursor_instance.parameters == ("C1",)
    assert connection.cursor_instance.statement.lstrip().startswith("SELECT")


def test_fetch_comparison_binds_company_and_metric_and_excludes_audit_fields():
    connection = FakeConnection(
        [("C1", "revenue", "2026Q2", 120.0, "2025Q4", 100.0, 20.0, 0.2, "up")],
        [
            "company_id",
            "metric_id",
            "current_period_id",
            "current_value",
            "previous_period_id",
            "previous_value",
            "change_value",
            "change_pct",
            "direction",
        ],
    )

    rows = fetch_comparison(connection, config(), "C1", "revenue")

    assert rows[0]["change_pct"] == 0.2
    assert connection.cursor_instance.parameters == ["C1", "revenue"]
    assert "gold_record_hash" not in connection.cursor_instance.statement
    assert "computed_at" not in connection.cursor_instance.statement