from __future__ import annotations

import os

import pytest

from apps.gold_viewer.gold_data import GoldConfig, fetch_companies, fetch_company_metrics, fetch_comparison, fetch_editorial_news, fetch_editorial_news_all, fetch_news_all, fetch_comparison_all, fetch_latest_finance_provenance_all, fetch_latest_finance_attempts, fetch_official_news_counts, fetch_finance_document_periods, fetch_finance_provenance, fetch_latest_finance_audit, fetch_latest_finance_provenance, fetch_latest_news_ai_audit, fetch_metric_history, fetch_news


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

    monkeypatch.setenv("GOLD_NEWS_TABLE", "gold_news")
    loaded = GoldConfig.from_environment()
    assert loaded.qualified_table == "`workspace`.`default`.`vigie_slice4_gold`"
    assert loaded.news_table == "gold_news"


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


def test_fetch_metric_history_is_quarterly_read_only():
    connection = FakeConnection([("MFC", "core_earnings", "2024-Q2", 1.2)], ["company_id", "metric_id", "period_id", "value"])

    rows = fetch_metric_history(connection, config(), "core_earnings")

    assert rows[0]["period_id"] == "2024-Q2"
    assert connection.cursor_instance.parameters == ("core_earnings",)
    assert "RLIKE" in connection.cursor_instance.statement
    assert connection.cursor_instance.statement.lstrip().startswith("SELECT")


def test_fetch_latest_news_ai_audit_is_read_only():
    columns = ["run_id", "model_calls", "max_model_calls"]
    connection = FakeConnection([("run-1", 3, 10)], columns)

    row = fetch_latest_news_ai_audit(connection, config())

    assert row == {"run_id": "run-1", "model_calls": 3, "max_model_calls": 10}
    assert connection.cursor_instance.statement.lstrip().startswith("SELECT")
    assert "ORDER BY observed_at DESC" in connection.cursor_instance.statement


def test_fetch_news_uses_deterministic_and_model_company_provenance():
    connection = FakeConnection([], [])
    fetch_news(connection, config(), "MFC")
    assert connection.cursor_instance.parameters == ["MFC"]
    assert "array_contains(relevant_company_ids, ?)" in connection.cursor_instance.statement
    assert "source_type" not in connection.cursor_instance.statement


def test_fetch_finance_provenance_binds_company_and_period():
    columns = ["company_id", "reporting_period", "source_url", "fetched_at"]
    connection = FakeConnection([("MFC", "2026-Q2", "https://www.manulife.com/report.pdf", "now")], columns)
    row = fetch_finance_provenance(connection, config(), "MFC", "2026-Q2")
    assert row["reporting_period"] == "2026-Q2"
    assert connection.cursor_instance.parameters == ("MFC", "2026-Q2")
    assert "acquisition_status IN" in connection.cursor_instance.statement


def test_fetch_latest_finance_provenance_binds_company_only():
    columns = ["company_id", "reporting_period", "source_url", "fetched_at"]
    connection = FakeConnection([("MFC", "2026-Q2", "https://www.manulife.com/report.pdf", "now")], columns)
    row = fetch_latest_finance_provenance(connection, config(), "MFC")
    assert row["reporting_period"] == "2026-Q2"
    assert connection.cursor_instance.parameters == ("MFC",)
    assert "ORDER BY reporting_period DESC" in connection.cursor_instance.statement


def test_fetch_finance_document_periods_is_traceable_and_quarterly():
    connection = FakeConnection([], [])
    fetch_finance_document_periods(connection, config())
    assert "source_url" in connection.cursor_instance.statement
    assert "reporting_period RLIKE" in connection.cursor_instance.statement
    assert connection.cursor_instance.statement.lstrip().startswith("SELECT")


def test_fetch_editorial_news_includes_company_and_general_industry_articles():
    connection = FakeConnection([], [])
    fetch_editorial_news(connection, config(), "MFC")
    assert connection.cursor_instance.parameters == ["MFC"]
    assert "editorial_news" in connection.cursor_instance.statement
    assert "INTERVAL 365 DAYS" in connection.cursor_instance.statement
    assert "array_contains(relevant_company_ids, ?)" in connection.cursor_instance.statement
    assert "COALESCE(size(relevant_company_ids), 0) = 0" in connection.cursor_instance.statement


def test_fetch_latest_finance_audit_exposes_ai_and_retention_counters():
    columns = ["run_id", "ai_model_calls", "retention_deleted_files"]
    connection = FakeConnection([("run-2", 0, 1)], columns)
    row = fetch_latest_finance_audit(connection, config())
    assert row == {"run_id": "run-2", "ai_model_calls": 0, "retention_deleted_files": 1}
    assert "ORDER BY observed_at DESC" in connection.cursor_instance.statement


def test_official_news_window_keeps_articles_without_a_publication_date():
    connection = FakeConnection([], ["article_id"])
    fetch_news(connection, config(), "MFC")
    statement = connection.cursor_instance.statement
    assert "COALESCE(published_at, fetched_at) >= current_timestamp() - INTERVAL 365 DAYS" in statement
    assert "published_at >= current_timestamp()" not in statement.replace("COALESCE(published_at, fetched_at) >= current_timestamp()", "")


def test_sidebar_status_queries_are_read_only_and_share_the_news_filters():
    connection = FakeConnection([], ["company_id", "n", "last_fetch"])
    fetch_official_news_counts(connection, config())
    statement = connection.cursor_instance.statement
    assert statement.lstrip().startswith("SELECT") and "explode(relevant_company_ids)" in statement
    assert "enrichment_status = 'succeeded'" in statement and "INTERVAL 365 DAYS" in statement
    connection = FakeConnection([], ["company_id"])
    fetch_latest_finance_attempts(connection, config())
    statement = connection.cursor_instance.statement
    assert statement.lstrip().startswith("SELECT") and "PARTITION BY company_id" in statement
    assert "acquisition_status" in statement and "error_code" in statement
    for forbidden in ("INSERT", "UPDATE", "DELETE", "MERGE", "DROP"):
        assert forbidden not in statement.upper().split()


class AmbiguousArray(list):
    """Behaves like the numpy arrays the SQL connector returns: its truth value is ambiguous."""

    def __bool__(self):
        raise ValueError("The truth value of an array is ambiguous")


def test_batched_reads_group_rows_per_company_and_survive_connector_arrays():
    columns = ["article_id", "relevant_company_ids", "published_at"]
    rows = [("a1", AmbiguousArray(["MFC"]), 3), ("a2", AmbiguousArray([]), 2), ("a3", AmbiguousArray(["SLF", "MFC"]), 1)]
    connection = FakeConnection(rows, columns)
    grouped = fetch_editorial_news_all(connection, config(), ["MFC", "SLF", "IAG"])
    assert [row["article_id"] for row in grouped["MFC"]] == ["a1", "a2", "a3"]
    assert [row["article_id"] for row in grouped["SLF"]] == ["a2", "a3"]  # untagged applies to everyone
    assert [row["article_id"] for row in grouped["IAG"]] == ["a2"]
    assert connection.cursor_instance.statement.lstrip().startswith("SELECT") and "LIMIT" not in connection.cursor_instance.statement

    comparison = FakeConnection([("MFC", "core_eps"), ("SLF", "core_eps"), ("MFC", "net_income")], ["company_id", "metric_id"])
    by_company = fetch_comparison_all(comparison, config(), ["MFC", "SLF", "GWO"])
    assert [row["metric_id"] for row in by_company["MFC"]] == ["core_eps", "net_income"] and by_company["GWO"] == []
    assert comparison.cursor_instance.statement.count("?") == 3 and comparison.cursor_instance.parameters == ["MFC", "SLF", "GWO"]

    documents = FakeConnection([("MFC", "2026-Q2")], ["company_id", "reporting_period"])
    latest = fetch_latest_finance_provenance_all(documents, config(), ["MFC", "SLF"])
    assert latest["MFC"]["reporting_period"] == "2026-Q2" and latest["SLF"] is None
    assert "PARTITION BY company_id" in documents.cursor_instance.statement and "'fetched', 'unchanged'" in documents.cursor_instance.statement

    news = FakeConnection([("n1", "MFC")], ["article_id", "news_company"])
    official = fetch_news_all(news, config(), ["MFC", "SLF"])
    assert official["MFC"] == [{"article_id": "n1"}] and official["SLF"] == []
    statement = news.cursor_instance.statement
    assert "explode(relevant_company_ids)" in statement and "news_rank <= 20" in statement and "INTERVAL 365 DAYS" in statement
