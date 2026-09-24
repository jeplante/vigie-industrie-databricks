import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_preview_displays_all_issuers_without_exposing_candidates(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class View:
        def __init__(self):
            self.rows = []
        def dataframe(self, rows, **kwargs):
            self.rows = rows
        def __getattr__(self, name):
            return lambda *args, **kwargs: None
    view = View()
    module.render_pnc_preview(view)
    assert len(view.rows) == 4
    assert all(row["Résultat net"] == "N/A" for row in view.rows)
    assert all(row["Période publiée"] == "N/A" for row in view.rows)


def test_current_period_does_not_fall_back_to_stale_values(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "apps/gold_viewer"))
    from pnc_data import current_pnc_rows
    rows = [dict(company_id="TD", metric_id="net_income", period_id="2026-Q2"),
            dict(company_id="DFY", metric_id="net_income", period_id="2026-Q1")]
    period, current = current_pnc_rows(rows)
    assert period == "2026-Q2"
    assert current == [rows[0]]


def test_preview_warns_when_fiscal_and_calendar_quarters_differ(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.warnings = []

        def warning(self, message):
            self.warnings.append(message)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    rows = [
        dict(company_id="TD", metric_id="net_income", period_id="2026-Q3",
             period_end="2026-07-31", calendar_basis="fiscal", value=0.279,
             unit="CAD_BILLION", source_url="https://example.com/td"),
        dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q3",
             period_end="2026-09-30", calendar_basis="calendar", value=94.9,
             unit="PERCENT", source_url="https://example.com/ifc"),
    ]
    view = View()
    module.render_pnc_preview(view, rows)
    assert len(view.warnings) == 1
    assert "TD Insurance : 2026-07-31" in view.warnings[0]
    assert "Intact Financial : 2026-09-30" in view.warnings[0]


def test_operating_net_income_is_labeled_as_non_ifrs(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.rows = []
            self.captions = []

        def dataframe(self, rows, **kwargs):
            self.rows = rows

        def caption(self, message):
            self.captions.append(message)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    row = dict(company_id="IFC", metric_id="operating_income", period_id="2026-Q2",
               period_end="2026-06-30", calendar_basis="calendar", value=0.561,
               unit="CAD_BILLION", source_url="https://example.com/ifc")
    view = View()
    module.render_pnc_preview(view, [row])
    assert view.rows[0]["Résultat net opérationnel"] == "0.561 G$ CA"
    assert any("non-IFRS" in caption for caption in view.captions)


def test_aviva_half_year_source_is_separate_from_quarterly_values(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.rows = []
            self.links = []
            self.info_messages = []

        def dataframe(self, rows, **kwargs):
            self.rows = rows

        def link_button(self, label, url, **kwargs):
            self.links.append((label, url))

        def info(self, message):
            self.info_messages.append(message)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    row = dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2",
               period_end="2026-06-30", calendar_basis="calendar", value=94.9,
               unit="PERCENT", source_url="https://example.com/ifc")
    view = View()
    module.render_pnc_preview(view, [row])
    aviva = next(item for item in view.rows if item["Compagnie"] == "Aviva Canada")
    assert aviva["Ratio combiné"] == "N/A"
    assert any("six mois" in message for message in view.info_messages)
    assert any(url == module.AVIVA_HY26_URL for _, url in view.links)


def test_pnc_history_retains_prior_quarter_fiscal_close_and_source(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.tables = []
            self.column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)

        def dataframe(self, rows, **kwargs):
            self.tables.append((rows, kwargs))

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    rows = [
        dict(company_id="TD", metric_id="net_income", period_id="2026-Q1",
             period_end="2026-01-31", calendar_basis="fiscal", value=.183,
             unit="CAD_BILLION", source_url="https://example.com/td-q1"),
        dict(company_id="TD", metric_id="net_income", period_id="2026-Q2",
             period_end="2026-04-30", calendar_basis="fiscal", value=.279,
             unit="CAD_BILLION", source_url="https://example.com/td-q2"),
        dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q1",
             period_end="2026-03-31", calendar_basis="calendar", value=91.3,
             unit="PERCENT", source_url="https://example.com/ifc-q1"),
    ]
    view = View()
    module.render_pnc_preview(view, rows)
    current, history = view.tables
    assert next(row for row in current[0] if row["Compagnie"] == "TD Insurance")["Résultat net"] == "0.279 G$ CA"
    assert [row["Trimestre"] for row in history[0]] == ["2026-Q2", "2026-Q1", "2026-Q1"]
    q1_td = next(row for row in history[0] if row["Compagnie"] == "TD Insurance" and row["Trimestre"] == "2026-Q1")
    assert q1_td["Valeur"] == "0.183 G$ CA"
    assert q1_td["Clôture"] == "2026-01-31"
    assert q1_td["Calendrier"] == "Fiscal"
    assert q1_td["Rapport officiel"] == "https://example.com/td-q1"
    assert "Rapport officiel" in history[1]["column_config"]
