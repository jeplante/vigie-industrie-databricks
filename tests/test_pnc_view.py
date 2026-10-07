import importlib.util
import sys
from datetime import datetime, timezone
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
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py
    class View:
        def __init__(self):
            self.html = ""
        def markdown(self, html, **kwargs):
            self.html += html
        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

        def __getattr__(self, name):
            return lambda *args, **kwargs: None
    view = View()
    module.render_pnc_page(view)
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
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py

    class View:
        def __init__(self):
            self.warnings = []

        def warning(self, message):
            self.warnings.append(message)

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

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
    module.render_pnc_page(view, rows)
    assert len(view.warnings) == 1
    assert "TD Insurance : 2026-07-31" in view.warnings[0]
    assert "Intact Financial : 2026-09-30" in view.warnings[0]


def test_operating_net_income_is_labeled_as_non_ifrs(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py

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

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    row = dict(company_id="IFC", metric_id="operating_income", period_id="2026-Q2",
               period_end="2026-06-30", calendar_basis="calendar", value=0.561,
               unit="CAD_BILLION", source_url="https://example.com/ifc")
    view = View()
    module.render_pnc_page(view, [row])
    assert "<strong>0.561 G$</strong>" in _row_html(view.html, "Intact Financial")
    assert "non-IFRS" in view.html  # column tooltip
    assert any("non-IFRS" in caption for caption in view.captions)


def test_aviva_half_year_source_is_separate_from_quarterly_values(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py

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

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    row = dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2",
               period_end="2026-06-30", calendar_basis="calendar", value=94.9,
               unit="PERCENT", source_url="https://example.com/ifc")
    view = View()
    module.render_pnc_page(view, [row])
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
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py

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

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

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
    module.render_pnc_page(view, rows)
    history = next(table for table in view.tables if table[0] and "Trimestre" in table[0][0])
    assert "<strong>0.279 G$</strong>" in _row_html(view.html, "TD Insurance")
    assert [row["Trimestre"] for row in history[0]] == ["2026-Q2", "2026-Q1"]  # TD only: its own panel
    assert {row["Compagnie"] for row in history[0]} == {"TD Insurance"}
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
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py

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

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

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
    module.render_pnc_page(view, rows)
    assert view.tab_labels == [["Synthèse", "Par compagnie"], ["IFC", "AV", "TD", "DFY"]]
    assert ("Assureurs de dommages", "2 / 4") in view.metrics
    assert "Période de référence : 2026-Q2" in view.captions
    assert "<strong>IFC</strong><span class='source-text'>2026-Q2 · 1 KPI · clôture 2026-06-30 · Civil" in view.html
    assert "source-na'><span class='source-state'>N/A</span><strong>AV</strong>" in view.html
    assert "source-na'><span class='source-state'>N/A</span><strong>DFY</strong>" in view.html
    assert any("Aucun indicateur validé pour 2026-Q2" in message for message in view.infos)  # AV and DFY panels


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
    module.render_pnc_chat = lambda *args, **kwargs: None  # chat covered in test_pnc_chat.py

    class View:
        def __init__(self):
            self.html = ""
            self.column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)

        sidebar = nullcontext()

        def tabs(self, labels):
            return [nullcontext() for _ in labels]

        def markdown(self, html, **kwargs):
            self.html += html

        def columns(self, spec):
            return [self] * (spec if isinstance(spec, int) else len(spec))

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    rows = [dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2", period_end="2026-06-30",
                 calendar_basis="calendar", value=94.9, unit="PERCENT", source_url="https://example.com/ifc")]
    acquisition = ([{"company_id": "IFC", "reporting_period": "2026-Q2", "acquisition_status": "unchanged", "fetched_at": "2026-10-07T01:43:56+00:00"}],
                   {"status": "needs_review", "candidate_count": 11, "observed_at": "2026-10-07T01:44:17+00:00", "missing_sources_json": '["AV"]'})
    with_audit, without = View(), View()
    module.render_pnc_page(with_audit, rows, (), acquisition)
    module.render_pnc_page(without, rows, ())
    assert "Dernier run" in with_audit.html and "lacune déclarée" in with_audit.html
    assert "Dernier run" not in without.html  # no read access: the section is simply absent


def test_pnc_news_read_is_read_only_and_bounded_to_the_namespace():
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
    assert module.fetch_pnc_news(connection, "workspace", "vigie") == ([], [], None, [])
    assert len(connection.statements) == 4 and all(s.lstrip().startswith("SELECT") for s in connection.statements)
    assert "`workspace`.`vigie`.`pnc_official_news`" in connection.statements[0] and "LIMIT 60" in connection.statements[0]
    assert "COALESCE(published_at, fetched_at)" in connection.statements[0] and "`pnc_news_audit`" in connection.statements[2]
    assert "`workspace`.`vigie`.`pnc_editorial_news`" in connection.statements[3] and "LIMIT 60" in connection.statements[3]
    with pytest.raises(ValueError):
        module.fetch_pnc_news(connection, "workspace", "vigie`; DROP")


def test_pnc_sector_media_read_tolerates_a_missing_table_and_numpy_arrays():
    import pytest

    module = _load_pnc_data()

    class AmbiguousArray(list):  # numpy arrays refuse truthiness, as the SQL connector returns ARRAY columns
        def __bool__(self): raise ValueError("ambiguous truth value")

    class Cursor:
        def __init__(self, owner): self.owner, self.rows = owner, []
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement):
            if "pnc_editorial_news" in statement and self.owner.missing:
                raise RuntimeError("[TABLE_OR_VIEW_NOT_FOUND] pnc_editorial_news")
            if "pnc_editorial_news" in statement and self.owner.broken:
                raise RuntimeError("PERMISSION_DENIED")
            self.description = [("article_id",), ("relevant_company_ids",), ("categories",)]
            self.rows = [("a1", AmbiguousArray(["IFC", "DFY"]), AmbiguousArray(["Médias assurance"]))] if "pnc_editorial_news" in statement else []
        def fetchall(self): return self.rows

    class Connection:
        def __init__(self, missing=False, broken=False): self.missing, self.broken = missing, broken
        def cursor(self): return Cursor(self)

    editorial = module.fetch_pnc_news(Connection(), "workspace", "vigie")[3]
    assert editorial == [{"article_id": "a1", "relevant_company_ids": ["IFC", "DFY"], "categories": ["Médias assurance"]}]
    assert type(editorial[0]["relevant_company_ids"]) is list
    assert module.fetch_pnc_news(Connection(missing=True), "workspace", "vigie")[3] == []
    with pytest.raises(RuntimeError):  # any other failure is not silenced
        module.fetch_pnc_news(Connection(broken=True), "workspace", "vigie")


def test_pnc_news_tab_lists_articles_and_filters_by_issuer_source_and_category(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Column:
        def __init__(self, view, name): self.view, self.name = view, name
        def multiselect(self, label, options, key=None):
            self.view.options[label] = list(options)
            return self.view.choices.get(label, [])

    class View:
        def __init__(self, choices=None):
            self.choices, self.options, self.titles, self.links, self.captions = choices or {}, {}, [], [], []
        def columns(self, count): return [Column(self, name) for name in range(count)]
        def markdown(self, text, **kwargs):
            if text.startswith("**"): self.titles.append(text.split("**")[1])
        def caption(self, text): self.captions.append(text)
        def write(self, text): pass
        def link_button(self, label, url, key=None): self.links.append((url, key))

    articles = [
        {"article_id": "1", "company_id": "IFC", "source": "intact_newsroom", "source_url": "https://newsroom.intactfc.com/a", "title": "Q3 catastrophe loss estimate",
         "summary": "s", "published_at": datetime(2026, 10, 6, tzinfo=timezone.utc), "categories": ["Résultats et capital"]},
        {"article_id": "2", "company_id": "AV", "source": "aviva_canada_press", "source_url": "https://www.aviva.ca/en/press-releases/2026/x/", "title": "Appoints Chief Claims Officer",
         "summary": "", "published_at": None, "categories": ["Communiqué"]},
    ]
    view = View()
    module.render_pnc_news(view, articles)
    assert view.titles == ["Q3 catastrophe loss estimate", "Appoints Chief Claims Officer"] and len(view.links) == 2
    assert view.options["Assureur"] == ["Intact Financial", "Aviva Canada"] and "Communiqué" in view.options["Catégorie"]
    only = View({"Assureur": ["Aviva Canada"]})
    module.render_pnc_news(only, articles)
    assert only.titles == ["Appoints Chief Claims Officer"]
    none = View({"Assureur": ["Intact Financial"], "Catégorie": ["Communiqué"]})
    module.render_pnc_news(none, articles)
    assert none.titles == [] and "Aucune actualité ne correspond aux filtres choisis." in none.captions
    empty = View()
    module.render_pnc_news(empty, [])
    assert any("Aucune actualité n’est encore disponible" in caption for caption in empty.captions)


def test_company_table_mirrors_the_life_columns_and_keeps_the_na_semantics():
    module = _load_pnc_view()
    current = [
        dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2", period_end="2026-06-30", calendar_basis="calendar", value=94.9, unit="PERCENT", source_url="u"),
        dict(company_id="IFC", metric_id="net_income", period_id="2026-Q2", period_end="2026-06-30", calendar_basis="calendar", value=0.867, unit="CAD_BILLION", source_url="u"),
    ]
    history = current + [
        dict(company_id="IFC", metric_id="combined_ratio", period_id="2025-Q2", period_end="2025-06-30", calendar_basis="calendar", value=86.1, unit="PERCENT", source_url="u"),
        dict(company_id="IFC", metric_id="net_income", period_id="2025-Q2", period_end="2025-06-30", calendar_basis="fiscal", value=0.5, unit="CAD_BILLION", source_url="u"),
    ]
    table = {row["Indicateur"]: row for row in module.pnc_company_table(current, history, "2026-Q2")}
    assert set(next(iter(table.values()))) == {"Indicateur", "Période", "Valeur", "Variation annuelle", "Comparaison"}
    assert table["Ratio combiné"]["Valeur"] == "94.9 %" and table["Ratio combiné"]["Variation annuelle"] == "▲ +8.8 pp"
    assert table["Résultat net"]["Valeur"] == "0.867 G$" and table["Résultat net"]["Variation annuelle"] == "N/A"  # fiscal vs civil: blocked
    assert table["Résultat net"]["Comparaison"] == "vs 2025-Q2"
    assert table["Ratio de sinistres"]["Valeur"] == "N/A" and table["Ratio de sinistres"]["Variation annuelle"] == "N/A"
    assert module.pnc_company_table([], [], None)[0]["Période"] == "N/A"


def test_company_panel_shows_provenance_history_news_and_the_aviva_gap():
    module = _load_pnc_view()

    class View:
        def __init__(self):
            self.infos, self.captions, self.links, self.tables, self.html = [], [], [], [], ""
            self.column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)
        def subheader(self, text): self.captions.append(text)
        def info(self, text): self.infos.append(text)
        def caption(self, text): self.captions.append(text)
        def link_button(self, label, url, key=None): self.links.append((label, key))
        def dataframe(self, rows, **kwargs): self.tables.append(rows)
        def markdown(self, text, **kwargs): self.html += text
        def columns(self, count): return [SimpleNamespace(multiselect=lambda *a, **k: []) for _ in range(count)]
        def write(self, text): pass

    current = [dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2", period_end="2026-06-30", calendar_basis="calendar", value=94.9, unit="PERCENT", source_url="https://example.com/ifc")]
    older = [dict(current[0], period_id="2025-Q2", period_end="2025-06-30", value=86.1)]
    news = [{"article_id": "n1", "company_id": "IFC", "source": "intact_newsroom", "source_url": "https://newsroom.intactfc.com/a", "title": "Catastrophe loss estimate",
             "summary": "", "published_at": None, "categories": ["Communiqué"]},
            {"article_id": "n2", "company_id": "DFY", "source": "definity_newsroom", "source_url": "https://www.definityfinancial.com/b", "title": "Other issuer", "summary": "", "published_at": None, "categories": []}]
    view = View()
    module.render_pnc_company(view, "IFC", "Intact Financial", "Groupe consolidé", current, current + older, "2026-Q2", news)
    assert "Périmètre : Groupe consolidé" in view.captions and any("Clôture : 2026-06-30 · Calendrier : Civil" in c for c in view.captions)
    assert ("Consulter le rapport officiel ↗", "pnc-report-IFC-0") in view.links
    assert any("Ratio combiné : 94.9 % (▲ +8.8 pp vs 2025-Q2)" in info for info in view.infos)
    assert len(view.tables) == 2 and "Trimestre" in view.tables[1][0]  # indicators, then its own two-quarter history
    assert "#### Actualités" in view.html and "Catastrophe loss estimate" in view.html and "Other issuer" not in view.html
    aviva = View()
    module.render_pnc_company(aviva, "AV", "Aviva Canada", "Segment Canada", [], [], "2026-Q2", [])
    assert any("Aucun indicateur validé pour 2026-Q2" in info for info in aviva.infos) and any("six mois" in info for info in aviva.infos)
    assert any(key == "pnc-company-aviva-hy26" for _label, key in aviva.links) and len(aviva.tables) == 1
    assert any("Aucune actualité pertinente" in caption for caption in aviva.captions)


def _load_pnc_view():
    path = Path(__file__).resolve().parents[1] / "apps/gold_viewer/pnc_view.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("pnc_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_history_spec_is_one_brand_coloured_line_per_issuer_with_report_links():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/gold_viewer"))
    import history_chart

    spec = history_chart.history_spec(
        [dict(company_id="IFC", period_id="2026-Q1", display_value=91.4, source_url="https://x/ifc", closing="2026-03-31"),
         dict(company_id="DFY", period_id="2026-Q1", display_value=float("nan"), source_url=None, closing="2026-03-31")],
        (("closing", "Clôture"),))
    values = spec["data"]["values"]
    assert values[0]["issuer"] == "Intact Financial" and values[1]["display_value"] is None  # NaN never reaches the chart
    colour = spec["layer"][0]["encoding"]["color"]["scale"]
    assert colour["domain"] == ["Definity Financial", "Intact Financial"] and colour["range"] == ["#00857a", "#1a4f8b"]
    points = spec["layer"][1]["encoding"]
    assert points["href"] == {"field": "source_url"} and {"field": "closing", "title": "Clôture"} in points["tooltip"]


def test_pnc_history_records_mask_spikes_and_cumulate_per_own_calendar():
    module = _load_pnc_view()

    def row(company, period, value, basis="calendar", metric="operating_income"):
        return dict(company_id=company, metric_id=metric, period_id=period, value=value, unit="CAD_BILLION",
                    period_end="x", calendar_basis=basis, source_url=f"https://x/{company}/{period}")

    rows = [row("IFC", "2025-Q1", 0.5), row("IFC", "2025-Q2", 2.0), row("IFC", "2025-Q3", 0.6),
            row("TD", "2025-Q1", 0.2, "fiscal"), row("TD", "2025-Q2", 0.3, "fiscal"),
            row("IFC", "2025-Q1", 90.0, metric="combined_ratio")]
    records, masked = module.pnc_history_records(rows, "operating_income", ["IFC", "TD"])
    assert masked == 1 and next(r for r in records if r["period_id"] == "2025-Q2" and r["company_id"] == "IFC")["display_value"] is None
    assert {r["calendar"] for r in records if r["company_id"] == "TD"} == {"Fiscal"}
    cumulative, _ = module.pnc_history_records(rows, "operating_income", ["TD"], cumulative=True)
    assert [r["display_value"] for r in cumulative] == [0.2, 0.5]
    ifc, _ = module.pnc_history_records(rows, "operating_income", ["IFC"], cumulative=True)
    assert [r["display_value"] for r in ifc] == [0.5, None, None]  # stops after the masked quarter
    volatile = [dict(r, metric_id="net_income") for r in rows if r["metric_id"] == "operating_income"]
    net, masked = module.pnc_history_records(volatile, "net_income", ["IFC"], cumulative=True)
    assert masked == 0 and [r["display_value"] for r in net] == [0.5, 2.5, 3.1]  # net income: never masked, still cumulated
    ratio, masked = module.pnc_history_records(rows, "combined_ratio", ["IFC"], cumulative=True)
    assert masked == 0 and ratio[0]["display_value"] == 90.0  # a ratio is never summed


def test_pnc_page_draws_the_history_chart_with_the_life_controls():
    module = _load_pnc_view()

    class View:
        sidebar = nullcontext()
        column_config = SimpleNamespace(LinkColumn=lambda *args, **kwargs: kwargs)

        def __init__(self): self.charts, self.selects, self.session_state = [], [], {}
        def tabs(self, labels): return [nullcontext() for _ in labels]
        def columns(self, spec): return [self] * (spec if isinstance(spec, int) else len(spec))
        def selectbox(self, label, options, **kwargs):
            self.selects.append((label, list(options), kwargs.get("disabled")))
            return list(options)[kwargs.get("index", 0)]
        def multiselect(self, label, options, default=None, **kwargs): return list(default or [])
        def vega_lite_chart(self, spec, **kwargs): self.charts.append(spec)
        def __getattr__(self, name): return lambda *args, **kwargs: None

    rows = [dict(company_id="IFC", metric_id="combined_ratio", period_id=period, period_end="x", calendar_basis="calendar",
                 value=value, unit="PERCENT", source_url="https://x") for period, value in (("2025-Q2", 90.0), ("2026-Q2", 94.9))]
    view = View()
    module.render_pnc_page(view, rows)
    assert len(view.charts) == 1 and len(view.charts[0]["data"]["values"]) == 2
    indicator = next(select for select in view.selects if select[0] == "Indicateur")
    basis = next(select for select in view.selects if select[0] == "Base")
    assert indicator[1] == ["combined_ratio"] and basis[2] is True  # a ratio cannot be cumulated


def test_pnc_news_mixes_official_and_sector_media_with_a_type_filter(monkeypatch):
    module = _load_pnc_view()

    class Column:
        def __init__(self, view): self.view = view
        def multiselect(self, label, options, key=None):
            self.view.options[label] = list(options)
            return self.view.choices.get(label, [])

    class View:
        def __init__(self, choices=None): self.choices, self.options, self.titles, self.captions = choices or {}, {}, [], []
        def columns(self, count): return [Column(self) for _ in range(count)]
        def markdown(self, text, **kwargs):
            if text.startswith("**"): self.titles.append(text)
        def caption(self, text): self.captions.append(text)
        def write(self, text): pass
        def link_button(self, *args, **kwargs): pass

    official = [{"article_id": "1", "company_id": "IFC", "source": "intact_newsroom", "source_url": "https://newsroom.intactfc.com/a",
                 "title": "Intact release", "summary": "", "published_at": datetime(2026, 10, 1, tzinfo=timezone.utc), "categories": ["Communiqué"]}]
    editorial = [{"article_id": "2", "relevant_company_ids": ["IFC", "AV"], "source": "insurance_journal", "source_url": "https://www.insurancejournal.com/b",
                  "title": "Intact and Aviva in the news", "summary": "", "published_at": datetime(2026, 10, 5, tzinfo=timezone.utc), "categories": ["Médias assurance"]}]
    view = View()
    module.render_pnc_news(view, official, editorial=editorial)
    assert [title.split("**")[1] for title in view.titles] == ["Intact and Aviva in the news", "Intact release"]  # newest first
    assert view.options["Type"] == ["Source officielle", "Média sectoriel"] or set(view.options["Type"]) == {"Source officielle", "Média sectoriel"}
    assert "Intact Financial, Aviva Canada · Insurance Journal · Média sectoriel" in view.titles[0]
    aviva = View()
    module.render_pnc_news(aviva, official, company="AV", editorial=editorial)
    assert [title.split("**")[1] for title in aviva.titles] == ["Intact and Aviva in the news"]
    only_official = View({"Type": ["Source officielle"]})
    module.render_pnc_news(only_official, official, editorial=editorial)
    assert [title.split("**")[1] for title in only_official.titles] == ["Intact release"]
