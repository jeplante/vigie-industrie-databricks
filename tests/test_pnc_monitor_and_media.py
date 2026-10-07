"""P&C parity with the life side: operations monitoring, sector media and the shared news publication rule."""
from datetime import UTC, datetime
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from vigie_databricks.operations_monitor import (PNC_EXPECTED_METRICS, announced_results_period, evaluate_pnc,
                                                 latest_completed_pnc_quarter)
from vigie_databricks.pnc_news import (EditorialSource, NewsResult, collect_pnc_editorial, load_editorial_sources,
                                       mentioned_issuers)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 8, 10, 45, tzinfo=UTC)


def published(period_by_company=None, **values):
    """Every expected KPI for each issuer's expected quarter, with plausible ratios."""
    period_by_company = period_by_company or {"IFC": "2026-Q2", "DFY": "2026-Q2", "TD": "2026-Q3"}
    defaults = {"combined_ratio": 93.9, "claims_ratio": 62.8, "expense_ratio": 31.1, "net_income": 0.2, "operating_income": 0.2}
    defaults.update(values)
    return [{"company_id": company, "metric_id": metric, "period_id": period_by_company[company], "value": defaults[metric],
             "validation_status": "validated_quarterly"}
            for company, metrics in PNC_EXPECTED_METRICS.items() for metric in sorted(metrics)]


def test_each_issuer_is_expected_on_its_own_fiscal_calendar():
    assert latest_completed_pnc_quarter(NOW) == "2026-Q2"  # Q3 ended Sept 30: not yet reported
    assert latest_completed_pnc_quarter(NOW, 10) == "2026-Q3"  # TD's fiscal Q3 ended July 31
    assert latest_completed_pnc_quarter(datetime(2026, 9, 10, tzinfo=UTC), 10) == "2026-Q2"  # inside TD's reporting window
    assert latest_completed_pnc_quarter(datetime(2026, 2, 20, tzinfo=UTC), 10) == "2025-Q4"  # TD fiscal year ends Oct 31
    assert latest_completed_pnc_quarter(datetime(2026, 2, 20, tzinfo=UTC)) == "2025-Q4"


def test_a_complete_and_plausible_publication_raises_nothing():
    assert evaluate_pnc(published(), [], now=NOW) == []


def test_a_missing_kpi_is_a_review_reminder_and_aviva_is_never_expected():
    rows = [row for row in published() if not (row["company_id"] == "TD")]
    alerts = evaluate_pnc(rows + [{"company_id": "AV", "metric_id": "combined_ratio", "period_id": "2024-Q1", "value": 92.4}], [], now=NOW)
    assert [(a.alert_type, a.severity, a.entity) for a in alerts] == [("pnc_quarter_incomplete", "warning", "TD")]
    assert "2026-Q3" in alerts[0].message and "net_income" in alerts[0].message


def test_implausible_ratios_and_a_broken_ratio_identity_are_critical():
    alerts = evaluate_pnc(published(expense_ratio=3.11), [], now=NOW)
    assert {(a.alert_type, a.severity, a.entity) for a in alerts} == {("pnc_value_anomalous", "critical", "DFY")}
    assert any("expense_ratio" in a.message for a in alerts) and any("ne donnent pas le ratio combiné" in a.message for a in alerts)
    assert evaluate_pnc(published(claims_ratio=62.4), [], now=NOW) == []  # 0.4 pp: rounding, tolerated


@pytest.mark.parametrize(("title", "period"), [
    ("Definity Financial Corporation Reports Second Quarter 2026 Results", "2026-Q2"),
    ("Intact Financial Corporation announces Q3-2026 results", "2026-Q3"),
    ("Intact Financial Corporation reports 2026 third-quarter results", "2026-Q3"),
    ("Definity Financial Corporation to announce second quarter 2026 results on July 30, 2026", None),
    ("Intact Financial Corporation announces third quarter catastrophe loss estimate", None),
    ("Definity releases estimate of financial impact from catastrophe losses for the third quarter of 2026", None),
    ("Definity Financial Corporation announces its 2026 annual meeting results", None),
    ("Media statement - Aviva Canada posts half-year 2026 results", None),
])
def test_results_release_titles(title, period):
    assert announced_results_period(title) == period


def test_announced_results_not_yet_published_raise_a_review_reminder():
    news = [{"company_id": "IFC", "title": "Intact Financial Corporation announces Q3-2026 results", "published_at": datetime(2026, 11, 4, tzinfo=UTC)},
            {"company_id": "DFY", "title": "Definity Financial Corporation Reports Second Quarter 2026 Results", "published_at": "2026-07-30"},
            {"company_id": "AV", "title": "Aviva Canada reports third quarter 2026 results", "published_at": "2026-11-05"}]
    alerts = evaluate_pnc(published(), news, now=datetime(2026, 11, 6, tzinfo=UTC))
    assert [(a.alert_type, a.entity) for a in alerts] == [("pnc_results_announced", "IFC")]  # DFY Q2 is published; AV is not expected
    assert "2026-Q3 annoncés le 2026-11-04" in alerts[0].message


def test_sector_media_keeps_only_dated_articles_naming_a_pnc_issuer():
    feed = """<rss><channel>
<item><title>Intact Financial buys a broker</title><link>https://media.example.com/a</link><pubDate>Tue, 06 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>The roof stayed intact</title><link>https://media.example.com/b</link><pubDate>Tue, 06 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Aviva and TD Insurance join a coalition</title><link>https://media.example.com/c</link><pubDate>Mon, 05 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Definity old news</title><link>https://media.example.com/d</link><pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate></item>
<item><title>Definity off-host</title><link>https://other.example.org/e</link><pubDate>Mon, 05 Oct 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""
    sources = [EditorialSource("media", "https://media.example.com/feed", ("media.example.com",)),
               EditorialSource("down", "https://down.example.com/feed", ("down.example.com",))]

    def fetch(url, hosts):
        if "down" in url:
            raise OSError("timeout")
        return feed

    result = collect_pnc_editorial(sources, fetch=fetch, now=datetime(2026, 10, 7, tzinfo=UTC))
    assert [(row["title"], row["relevant_company_ids"]) for row in result.rows] == [
        ("Intact Financial buys a broker", ["IFC"]), ("Aviva and TD Insurance join a coalition", ["AV", "TD"])]
    assert result.per_source["media"] == {"status": "ok", "items": 4, "articles": 2}
    assert result.per_source["down"]["status"] == "failed" and "timeout" in result.per_source["down"]["error"]
    assert mentioned_issuers("TD Bank Group results") == [] and mentioned_issuers("Economical Insurance") == ["DFY"]


def test_the_approved_sector_feeds_are_https_and_distinct():
    sources = load_editorial_sources(ROOT / "config/pnc/news_sources.yaml")
    assert [source.source_id for source in sources] == ["insurance_journal", "insurance_canada", "artemis", "reinsurance_news"]
    assert all(source.url.startswith("https://") for source in sources)


def test_pnc_news_task_fails_on_a_failed_newsroom_or_too_few_sector_feeds():
    from vigie_databricks.tasks.pnc_news import failures

    ok = NewsResult(per_source={"IFC": {"status": "ok"}, "AV": {"status": "ok"}})
    down = NewsResult(per_source={"IFC": {"status": "ok"}, "AV": {"status": "failed"}})
    media = NewsResult(per_source={"a": {"status": "ok"}, "b": {"status": "ok"}, "c": {"status": "failed"}})
    thin = NewsResult(per_source={"a": {"status": "ok"}, "b": {"status": "failed"}})
    assert failures(ok, media) == []
    assert failures(down, media) == ["P&C news sources failed: AV"]
    assert failures(ok, thin) == ["P&C sector media: 1 feed(s) answered, minimum 2"]


class _Frame:
    def __init__(self, spark, rows): self.spark, self.rows = spark, rows
    def select(self, *columns): return self
    def join(self, other, *args): return self
    def alias(self, name): return self
    def where(self, condition): return self
    def count(self): return len(self.rows)
    def createOrReplaceTempView(self, name): self.spark.views.append(name)

    @property
    def write(self):
        spark = self.spark
        rows = self.rows

        class Writer:
            def format(self, name): return self
            def mode(self, name): return self
            def option(self, *args): return self
            def saveAsTable(self, table): spark.saved.append((table, rows))
        return Writer()


class _Spark:
    def __init__(self):
        self.saved, self.sql_calls, self.views = [], [], []
        self.catalog = SimpleNamespace(tableExists=lambda table: True, dropTempView=lambda name: None)
    def createDataFrame(self, rows, schema=None): return _Frame(self, list(rows))
    def table(self, name): return _Frame(self, [])
    def sql(self, statement): self.sql_calls.append(statement)


def test_life_official_news_publishes_the_sources_that_answered_and_still_fails(monkeypatch):
    spark = _Spark()
    pyspark = ModuleType("pyspark")
    sql = ModuleType("pyspark.sql")
    sql.SparkSession = SimpleNamespace(builder=SimpleNamespace(getOrCreate=lambda: spark))
    monkeypatch.setitem(sys.modules, "pyspark", pyspark)
    monkeypatch.setitem(sys.modules, "pyspark.sql", sql)
    # import the task against the fake Spark, and let monkeypatch drop that copy again after the test
    monkeypatch.setitem(sys.modules, "vigie_databricks.tasks.official_news", None)
    monkeypatch.delitem(sys.modules, "vigie_databricks.tasks.official_news")
    import vigie_databricks.tasks as tasks_package
    monkeypatch.delattr(tasks_package, "official_news", raising=False)
    import importlib
    official_news = importlib.import_module("vigie_databricks.tasks.official_news")

    article = {"article_id": "a", "company_id": "SLF", "content_hash": "h"}

    def acquire(company):
        if company == "GWO":
            raise OSError("site down")
        return [dict(article, company_id=company, article_id=company)]

    monkeypatch.setattr(official_news, "acquire_official_news", acquire)
    monkeypatch.setattr(official_news, "acquire_manulife_news", lambda directory: [dict(article, company_id="MFC", article_id="MFC")])
    monkeypatch.setattr(sys, "argv", ["official_news", "--config-directory", "c", "--dry-run", "false"])
    with pytest.raises(ValueError, match="GWO"):
        official_news.main()
    assert any(statement.startswith("MERGE INTO workspace.vigie.official_news") for statement in spark.sql_calls)
    audit = [rows[0] for table, rows in spark.saved if table == "workspace.vigie.official_news_audit"]
    assert len(audit) == 1 and audit[0]["sources_succeeded"] == 3 and audit[0]["articles"] == 3
