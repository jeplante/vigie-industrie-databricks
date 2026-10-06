"""Slice 18 — presentation alignment tests. Pure rendering, no network, no Spark.

Validates that both universes render through the shared visual system while the
P&C universe keeps its domain guardrails (Périmètre / Clôture / Calendrier, N/A
semantics) and shows a year-over-year delta only when the comparison is
legitimate (same company, metric, prior-year same quarter, same calendar basis).
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import shared_ui
import comparison_table
import pnc_view


# --- shared layer ---------------------------------------------------------

def test_brand_registry_covers_both_universes():
    for company_id in ("MFC", "SLF", "GWO", "IAG", "IFC", "AV", "TD", "DFY"):
        name, colour = shared_ui.BRAND[company_id]
        assert name and colour.startswith("#")


def test_format_value_single_convention():
    assert shared_ui.format_value(1.234, "billion") == "1.234 G$"
    assert shared_ui.format_value(94.25, "percent") == "94.2 %"
    assert shared_ui.format_value(1.4, "assets", "total_client_assets") == "1.4 T$"
    assert shared_ui.format_value(None, "billion") == "—"


def test_vigie_header_structure():
    html = shared_ui.vigie_header("Eyebrow", "Titre", "Sous-titre")
    assert "vigie-header" in html and "vigie-eyebrow" in html and "<h1>Titre</h1>" in html


# --- life universe unchanged ---------------------------------------------

def _life_rows():
    return {
        "MFC": [
            {"metric_id": "core_earnings", "current_value": 1.8, "current_period_id": "2026-Q1",
             "previous_period_id": "2025-Q1", "direction": "up", "change_pct": 0.1, "change_value": None},
        ],
        "SLF": [], "GWO": [], "IAG": [],
    }


def test_life_table_keeps_brand_and_structure():
    html = comparison_table.comparison_html(_life_rows())
    assert "comparison-wrap" in html and "comparison-table" in html
    assert "--company-colour:#1677c8" in html          # Manuvie brand colour preserved
    assert "Manuvie" in html and "MFC.2026-Q1" in html  # ticker format preserved
    assert "1.800 G$" in html                           # shared formatter
    assert "comparison-empty" in html                   # N/A cells for empty issuers


# --- P&C universe aligned, guardrails intact ------------------------------

def _pnc_rows():
    base = dict(unit="CAD_BILLION", period_end="2026-03-31", calendar_basis="civil",
                disclosure_scope="group", source_url="https://example.com/ifc")
    return [
        {**base, "company_id": "IFC", "metric_id": "insurance_revenue", "period_id": "2026-Q1", "value": 6.123},
        {**base, "company_id": "IFC", "metric_id": "combined_ratio", "period_id": "2026-Q1",
         "value": 91.4, "unit": "PERCENT"},
        # prior-year same quarter, same calendar -> legitimate YoY
        {**base, "company_id": "IFC", "metric_id": "insurance_revenue", "period_id": "2025-Q1", "value": 5.500},
    ]


def test_pnc_table_uses_shared_system_and_keeps_meta_columns():
    html = pnc_view.pnc_comparison_html("2026-Q1", _pnc_rows(), _pnc_rows())
    assert "comparison-wrap" in html and "comparison-table" in html
    assert "--company-colour:#1a4f8b" in html           # Intact brand colour applied
    # guardrail columns present
    for column in ("Périmètre", "Clôture", "Calendrier"):
        assert column in html
    assert "Groupe consolidé" in html and "2026-03-31" in html and "Civil" in html
    assert "6.123 G$" in html and "91.4 %" in html       # shared formatter, both kinds
    assert "comparison-empty" in html                    # metrics without a row -> N/A


def test_pnc_yoy_only_when_legitimate():
    rows = _pnc_rows()
    # revenue has a valid prior-year same-quarter civil value -> delta shown
    revenue = next(r for r in rows if r["metric_id"] == "insurance_revenue" and r["period_id"] == "2026-Q1")
    assert "vs 2025-Q1" in pnc_view.pnc_delta(revenue, rows)
    # combined_ratio has no prior-year row -> no delta
    ratio = next(r for r in rows if r["metric_id"] == "combined_ratio")
    assert pnc_view.pnc_delta(ratio, rows) == ""


def test_pnc_yoy_blocked_across_calendar_bases():
    current = {"company_id": "TD", "metric_id": "net_income", "period_id": "2026-Q1",
               "value": 0.4, "unit": "CAD_BILLION", "calendar_basis": "fiscal"}
    prior_civil = {"company_id": "TD", "metric_id": "net_income", "period_id": "2025-Q1",
                   "value": 0.3, "unit": "CAD_BILLION", "calendar_basis": "civil"}
    assert pnc_view.pnc_delta(current, [current, prior_civil]) == ""


def test_pnc_delta_tone_is_neutral():
    # favourability differs by metric; the chip must never be coloured up/down
    rows = _pnc_rows()
    revenue = next(r for r in rows if r["metric_id"] == "insurance_revenue" and r["period_id"] == "2026-Q1")
    badge = pnc_view.pnc_delta(revenue, rows)
    assert "comparison-delta flat" in badge
    assert "comparison-delta up" not in badge and "comparison-delta down" not in badge


def test_pnc_conflicting_closes_raise():
    rows = [
        {"company_id": "IFC", "metric_id": "insurance_revenue", "period_id": "2026-Q1", "value": 6.0,
         "unit": "CAD_BILLION", "period_end": "2026-03-31", "calendar_basis": "civil", "source_url": "x"},
        {"company_id": "IFC", "metric_id": "net_income", "period_id": "2026-Q1", "value": 1.0,
         "unit": "CAD_BILLION", "period_end": "2026-02-28", "calendar_basis": "civil", "source_url": "x"},
    ]
    try:
        pnc_view.pnc_comparison_html("2026-Q1", rows, rows)
    except ValueError:
        return
    raise AssertionError("expected conflicting closing dates to raise")
