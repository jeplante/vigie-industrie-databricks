import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"))

from source_status import (alert_rows, audit_freshness_row, finance_sources, format_time, news_sources,
                           source_list_html, worst_level)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def good(period="2026-Q2"):
    return {"reporting_period": period, "fetched_at": datetime(2026, 10, 7, 10, 16, 36, tzinfo=timezone.utc)}


def by_name(rows):
    return {row.name: row for row in rows}


def test_finance_flags_the_failing_source_with_its_reason_and_the_last_good_period():
    rows = by_name(finance_sources(
        ["MFC", "SLF", "GWO", "IAG"],
        {"MFC": good(), "SLF": good("2026-Q1"), "GWO": None, "IAG": good()},
        {"MFC": {"acquisition_status": "unchanged"},
         "SLF": {"acquisition_status": "failed", "error_code": "http_503"},
         "IAG": {"acquisition_status": "fetched"}},
        "2026-Q2"))
    assert rows["MFC"].level == "ok" and "à jour" in rows["MFC"].text and "2026-10-07 10:16" in rows["MFC"].text
    assert rows["SLF"].level == "error" and "http_503" in rows["SLF"].text and "2026-Q1" in rows["SLF"].text
    assert rows["GWO"].level == "error" and "Aucun document" in rows["GWO"].text
    assert rows["IAG"].level == "ok"


def test_finance_flags_a_late_period_as_warning_not_error():
    (row,) = finance_sources(["MFC"], {"MFC": good("2026-Q1")}, {"MFC": {"acquisition_status": "unchanged"}}, "2026-Q2")
    assert row.level == "warn" and "2026-Q1" in row.text and "2026-Q2" in row.text


def test_news_lists_counts_and_flags_a_company_without_articles_and_partial_runs():
    counts = {"MFC": {"n": 1, "last_fetch": "2026-09-06T20:26:46+00:00"},
              "SLF": {"n": 6, "last_fetch": "2026-10-07 13:06:31+00:00"}}
    rows = by_name(news_sources(["MFC", "SLF", "IAG"], counts, {"sources_succeeded": 3}))
    assert rows["MFC"].text.startswith("1 article ·") and "2026-09-06 20:26" in rows["MFC"].text
    assert rows["SLF"].text.startswith("6 articles ·")
    assert rows["IAG"].level == "warn" and "Aucun article" in rows["IAG"].text
    assert rows["Dernier run"].level == "warn" and "3/4" in rows["Dernier run"].text


def test_a_stale_audit_is_flagged_even_though_runs_may_succeed():
    row = audit_freshness_row("Actualités officielles", {"observed_at": NOW - timedelta(days=22)}, NOW, 18, 72)
    assert row.level == "error" and "22 j" in row.text
    assert audit_freshness_row("x", {"observed_at": NOW - timedelta(hours=20)}, NOW, 18, 72).level == "warn"
    assert audit_freshness_row("x", {"observed_at": NOW - timedelta(hours=2)}, NOW, 18, 72) is None
    assert audit_freshness_row("x", None, NOW, 18, 72).level == "error"
    assert audit_freshness_row("x", {"observed_at": "2026-10-07 11:00:00+00:00"}, NOW, 18, 72) is None


def test_alerts_html_and_helpers_are_safe_and_explicit():
    rows = alert_rows([{"status": "alert", "entity": "vigie-gold-viewer", "message": "App=<STOPPED>"},
                       {"status": "healthy", "entity": "vigie", "message": "ok"}])
    assert [row.name for row in rows] == ["vigie-gold-viewer"] and worst_level(rows) == "error"
    html = source_list_html(rows)
    assert "&lt;STOPPED&gt;" in html and "Problème" in html and "<STOPPED>" not in html
    assert source_list_html([]) == "" and worst_level([]) == "ok"
    assert format_time(None) == "—" and format_time("2026-10-07T10:16:36.5+00:00") == "2026-10-07 10:16"
