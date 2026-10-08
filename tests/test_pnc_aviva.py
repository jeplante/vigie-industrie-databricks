"""Aviva Canada half-year and full-year ratios: read from its media statements, published apart from quarters."""
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from vigie_databricks.pnc_aviva import build_rows, discover_statements, extract_ratio, period_of, statement_text

FOOTNOTE = "* All COR results cited are on an undiscounted basis and premium growth is presented in constant currency."
HY26 = (f"<html><script>var x=1;</script><p>Aviva Canada continued its strong performance track record, achieving a HY26 "
        f"Combined Operating Ratio (COR*) of 93.0% and Gross Written Premium growth* of 3.0%.</p><p>{FOOTNOTE}</p></html>")
FY25 = f"<p>We ended FY25 in a strong position. Our FY25 Combined Operating Ratio (COR*) of 95.6% was driven mainly by personal lines.</p><p>{FOOTNOTE}</p>"
HY25 = f"<p>For HY25, Aviva Canada continued its track record, achieving a Combined Operating Ratio (COR*) of 94.7% despite weather.</p><p>{FOOTNOTE}</p>"


def test_titles_name_a_half_year_or_a_full_year():
    assert period_of("Media statement - Aviva Canada posts half-year 2026 results") == "2026-H1"
    assert period_of("Media statement - Aviva Canada posts half-year results 2026") == "2026-H1"
    assert period_of("Media statement - Aviva Canada posts full-year 2025 results") == "2025-FY"
    assert period_of("Aviva plc Q1 Trading Update") is None and period_of("Aviva Canada appoints Chief Claims Officer") is None


def test_the_ratio_is_read_only_for_its_own_period_on_an_undiscounted_basis():
    assert extract_ratio(statement_text(HY26), "2026-H1")[:2] == (93.0, None)
    assert extract_ratio(statement_text(FY25), "2025-FY")[:2] == (95.6, None)
    assert extract_ratio(statement_text(HY25), "2025-H1")[:2] == (94.7, None)  # label given at the start of the sentence
    assert extract_ratio(statement_text(HY26), "2025-H1")[1].startswith("ratio_period_mismatch")
    assert extract_ratio(statement_text(HY26.replace(FOOTNOTE, "")), "2026-H1")[1] == "undiscounted_basis_not_stated"
    assert extract_ratio(statement_text(HY26.replace("93.0%", "9.3%")), "2026-H1")[1] in ("combined_operating_ratio_not_found", "ratio_out_of_bounds (9.3)")


def test_discovery_skips_published_periods_and_foreign_links():
    news = [{"company_id": "AV", "title": "Media statement - Aviva Canada posts half-year 2026 results", "source_url": "https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/"},
            {"company_id": "AV", "title": "Media statement - Aviva Canada posts full-year 2025 results", "source_url": "https://www.aviva.ca/en/press-releases/2026/full-year-2025-results/"},
            {"company_id": "AV", "title": "Media statement - Aviva Canada posts half-year 2025 results", "source_url": "https://evil.example.org/x"},
            {"company_id": "IFC", "title": "Aviva Canada posts half-year 2024 results", "source_url": "https://www.aviva.ca/x"}]
    assert discover_statements(news, {"2025-FY"}) == [("2026-H1", "https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/")]


def test_rows_carry_their_own_status_and_evidence_and_a_failure_is_a_rejection():
    pages = {"https://www.aviva.ca/a": HY26, "https://www.aviva.ca/b": FY25}

    def fetch(url, hosts):
        if url not in pages:
            raise OSError("down")
        return pages[url]

    rows, decisions = build_rows([("2026-H1", "https://www.aviva.ca/a"), ("2025-FY", "https://www.aviva.ca/b"), ("2025-H1", "https://www.aviva.ca/c")],
                                 fetch, now=datetime(2026, 10, 8, tzinfo=UTC))
    assert [(r["observation_id"], r["value"], r["validation_status"], r["period_end"]) for r in rows] == [
        ("AV-2026-H1-combined_ratio", 93.0, "validated_semiannual", "2026-06-30"),
        ("AV-2025-FY-combined_ratio", 95.6, "validated_annual", "2025-12-31")]
    assert json.loads(rows[0]["evidence_json"])["reviewed_by"] == "automatic-checks-v1"
    assert [d["decision"] for d in decisions] == ["accepted", "accepted", "rejected"]


def test_half_years_never_enter_the_quarterly_views():
    from vigie_databricks.operations_monitor import evaluate_pnc
    from vigie_databricks.pnc_discovery import discover_manifest

    half = {"observation_id": "AV-2026-H1-combined_ratio", "company_id": "AV", "metric_id": "combined_ratio", "period_id": "2026-H1",
            "value": 93.0, "validation_status": "validated_semiannual"}
    assert evaluate_pnc([half], [], now=datetime(2026, 10, 8, tzinfo=UTC)) == evaluate_pnc([], [], now=datetime(2026, 10, 8, tzinfo=UTC))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/gold_viewer"))
    from pnc_data import current_pnc_rows
    assert current_pnc_rows([half]) == (None, [])


def test_aviva_panel_shows_half_years_apart_with_their_duration():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/gold_viewer"))
    import pnc_view

    half_years = [{"period_id": "2025-FY", "value": 95.6, "period_end": "2025-12-31", "source_url": "https://www.aviva.ca/b"},
                  {"period_id": "2026-H1", "value": 93.0, "period_end": "2026-06-30", "source_url": "https://www.aviva.ca/a"}]
    table = pnc_view.half_year_table(half_years)
    assert [(row["Période"], row["Ratio combiné"], row["Durée"]) for row in table] == [
        ("Premier semestre 2026", "93.0 %", "6 mois"), ("Année 2025", "95.6 %", "12 mois")]

    class View:
        def __init__(self): self.infos, self.tables, self.links = [], [], []
        column_config = SimpleNamespace(LinkColumn=lambda *a, **k: k)
        def info(self, text): self.infos.append(text)
        def dataframe(self, rows, **kwargs): self.tables.append(rows)
        def link_button(self, label, url, key=None): self.links.append(url)
        def __getattr__(self, name): return lambda *a, **k: None

    view = View()
    pnc_view.render_pnc_company(view, "AV", "Aviva Canada", "Segment Canada", [], [], "2026-Q2", half_years=half_years)
    assert view.tables[0] == table and any("93.0 % (premier semestre 2026, 6 mois)" in info for info in view.infos)
    assert view.links == ["https://www.aviva.ca/a"]


def test_task_publishes_new_statements_and_skips_published_ones(monkeypatch):
    from vigie_databricks import pnc_news, pnc_storage
    from vigie_databricks.tasks import pnc_acquire

    stored = []
    monkeypatch.setattr(pnc_storage, "publish_pnc_gold", lambda spark, namespace, rows: stored.extend(rows) or len(rows))
    monkeypatch.setattr(pnc_news, "http_get", lambda url, hosts: HY26)
    news = [SimpleNamespace(asDict=lambda: {"company_id": "AV", "title": "Media statement - Aviva Canada posts half-year 2026 results",
                                            "source_url": "https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/"})]
    spark = SimpleNamespace(sql=lambda statement: SimpleNamespace(collect=lambda: news))
    outcome = pnc_acquire._aviva_half_years(spark, "workspace.vigie", [], write=True)
    assert outcome["published"] == 1 and stored[0]["period_id"] == "2026-H1" and outcome["rejected"] == []
    published = [{"company_id": "AV", "period_id": "2026-H1", "validation_status": "validated_semiannual"}]
    assert pnc_acquire._aviva_half_years(spark, "workspace.vigie", published, write=True)["decisions"] == []
    dry = pnc_acquire._aviva_half_years(spark, "workspace.vigie", [], write=False)
    assert dry["published"] == 0 and [d["decision"] for d in dry["decisions"]] == ["accepted"] and len(stored) == 1
