import importlib.util
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace


def _row_html(html, company_name):
    """The <tr> of the shared branded table that belongs to one issuer."""
    return next(part for part in html.split("<tr style") if f"<strong>{company_name}</strong>" in part)


def test_preview_displays_all_issuers_without_exposing_candidates(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class View:
        def __init__(self):
            self.html = ""
        def markdown(self, html, **kwargs):
            self.html += html
        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def __getattr__(self, name):
            return lambda *args, **kwargs: None
    view = View()
    module.render_pnc_preview(view)
    assert view.html.count("<tr style") == 4
    for name in ("Intact Financial", "Aviva Canada", "TD Insurance", "Definity Financial"):
        row = _row_html(view.html, name)
        assert row.count("comparison-empty") == 6  # every metric is N/A, none invented
        assert row.count("comparison-meta'>N/A") == 2  # Clôture and Calendrier
        assert "comparison-period" not in row and "comparison-delta" not in row


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

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

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
            self.html = ""
            self.captions = []

        def markdown(self, html, **kwargs):
            self.html += html

        def caption(self, message):
            self.captions.append(message)

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    row = dict(company_id="IFC", metric_id="operating_income", period_id="2026-Q2",
               period_end="2026-06-30", calendar_basis="calendar", value=0.561,
               unit="CAD_BILLION", source_url="https://example.com/ifc")
    view = View()
    module.render_pnc_preview(view, [row])
    assert "<strong>0.561 G$</strong>" in _row_html(view.html, "Intact Financial")
    assert "non-IFRS" in view.html  # column tooltip
    assert any("non-IFRS" in caption for caption in view.captions)


def test_aviva_half_year_source_is_separate_from_quarterly_values(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.html = ""
            self.links = []
            self.info_messages = []

        def markdown(self, html, **kwargs):
            self.html += html

        def link_button(self, label, url, **kwargs):
            self.links.append((label, url))

        def info(self, message):
            self.info_messages.append(message)

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    row = dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2",
               period_end="2026-06-30", calendar_basis="calendar", value=94.9,
               unit="PERCENT", source_url="https://example.com/ifc")
    view = View()
    module.render_pnc_preview(view, [row])
    aviva = _row_html(view.html, "Aviva Canada")
    assert aviva.count("comparison-empty") == 6  # combined ratio stays N/A, with all other metrics
    assert "%" not in aviva
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
            self.html = ""
            self.column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)

        def dataframe(self, rows, **kwargs):
            self.tables.append((rows, kwargs))

        def markdown(self, html, **kwargs):
            self.html += html

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

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
    (history,) = view.tables
    assert "<strong>0.279 G$</strong>" in _row_html(view.html, "TD Insurance")
    assert [row["Trimestre"] for row in history[0]] == ["2026-Q2", "2026-Q1", "2026-Q1"]
    q1_td = next(row for row in history[0] if row["Compagnie"] == "TD Insurance" and row["Trimestre"] == "2026-Q1")
    assert q1_td["Valeur"] == "0.183 G$"
    assert q1_td["Clôture"] == "2026-01-31"
    assert q1_td["Calendrier"] == "Fiscal"
    assert q1_td["Rapport officiel"] == "https://example.com/td-q1"
    assert "Rapport officiel" in history[1]["column_config"]


def test_pnc_page_has_source_sidebar_and_summary_history_tabs(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.metrics, self.captions, self.tab_labels, self.infos, self.html = [], [], [], [], ""
            self.column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)

        sidebar = nullcontext()

        def tabs(self, labels):
            self.tab_labels.append(list(labels))
            return [nullcontext() for _ in labels]

        def metric(self, label, value, *args, **kwargs):
            self.metrics.append((label, value))

        def markdown(self, html, **kwargs):
            self.html += html

        def caption(self, message):
            self.captions.append(message)

        def info(self, message):
            self.infos.append(message)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    rows = [
        dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2",
             period_end="2026-06-30", calendar_basis="calendar", value=94.9,
             unit="PERCENT", source_url="https://example.com/ifc"),
        dict(company_id="TD", metric_id="net_income", period_id="2026-Q2",
             period_end="2026-04-30", calendar_basis="fiscal", value=0.279,
             unit="CAD_BILLION", source_url="https://example.com/td"),
    ]
    view = View()
    module.render_pnc_preview(view, rows)
    assert view.tab_labels == [["Synthèse", "Historique validé"]]
    assert ("Assureurs de dommages", "2 / 4") in view.metrics
    assert "Période de référence : 2026-Q2" in view.captions
    assert "<strong>IFC</strong><span class='source-text'>2026-Q2 · 1 KPI · clôture 2026-06-30 · Civil" in view.html
    assert "source-na'><span class='source-state'>N/A</span><strong>AV</strong>" in view.html
    assert "source-na'><span class='source-state'>N/A</span><strong>DFY</strong>" in view.html
    assert any("plusieurs trimestres" in message for message in view.infos)  # a single period: no history table


def test_pnc_acquisition_is_read_only_and_validates_the_namespace():
    import pytest

    module = _load_pnc_data()

    class Cursor:
        def __init__(self, owner): self.owner = owner; self.description = [("company_id",)]
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement): self.owner.statements.append(statement)
        def fetchall(self): return []

    class Connection:
        def __init__(self): self.statements = []
        def cursor(self): return Cursor(self)

    connection = Connection()
    assert module.fetch_pnc_acquisition(connection, "workspace", "vigie") == ([], None)
    assert len(connection.statements) == 2 and all(s.lstrip().startswith("SELECT") for s in connection.statements)
    assert "`workspace`.`vigie`.`pnc_financial_documents`" in connection.statements[0] and "PARTITION BY company_id" in connection.statements[0]
    assert "`pnc_run_audit`" in connection.statements[1] and "LIMIT 1" in connection.statements[1]
    with pytest.raises(ValueError):
        module.fetch_pnc_acquisition(connection, "workspace; DROP", "vigie")


def _load_pnc_data():
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_data.py"
    spec = importlib.util.spec_from_file_location("pnc_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pnc_sidebar_adds_an_acquisition_section_when_the_audit_is_readable(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class View:
        def __init__(self):
            self.html = ""
            self.column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def markdown(self, html, **kwargs):
            self.html += html

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    rows = [dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2", period_end="2026-06-30",
                 calendar_basis="calendar", value=94.9, unit="PERCENT", source_url="https://example.com/ifc")]
    acquisition = ([{"company_id": "IFC", "reporting_period": "2026-Q2", "acquisition_status": "unchanged", "fetched_at": "2026-10-07T01:43:56+00:00"}],
                   {"status": "needs_review", "candidate_count": 11, "observed_at": "2026-10-07T01:44:17+00:00", "missing_sources_json": '["AV"]'})
    with_audit, without = View(), View()
    module.render_pnc_preview(with_audit, rows, (), acquisition)
    module.render_pnc_preview(without, rows, ())
    assert "Dernier run" in with_audit.html and "lacune déclarée" in with_audit.html
    assert "Dernier run" not in without.html  # no read access: the section is simply absent
