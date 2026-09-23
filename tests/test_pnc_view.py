import importlib.util
from pathlib import Path


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
        dict(company_id="TD", metric_id="net_income", period_id="2026-Q2",
             period_end="2026-04-30", calendar_basis="fiscal", value=0.279,
             unit="CAD_BILLION", source_url="https://example.com/td"),
        dict(company_id="IFC", metric_id="combined_ratio", period_id="2026-Q2",
             period_end="2026-06-30", calendar_basis="calendar", value=94.9,
             unit="PERCENT", source_url="https://example.com/ifc"),
    ]
    view = View()
    module.render_pnc_preview(view, rows)
    assert len(view.warnings) == 1
    assert "30 avril" in view.warnings[0]
    assert "30 juin" in view.warnings[0]


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
