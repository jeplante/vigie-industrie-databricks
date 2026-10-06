"""Shared presentation layer consumed by both insurance universes.

Slice 18 extracts the visual system that the life-insurance comparison and the
P&C comparison have in common: the branded header, the brand-colour registry,
the single value formatter, and the branded-table primitives (row header,
period chip, delta badge, table shell). Each universe keeps its own domain
truths; only the rendering vocabulary is shared.
"""
from __future__ import annotations

from html import escape
from typing import Any

# Single source of brand identity for every issuer, both universes.
# Life colours are unchanged from the original comparison_table registry.
# P&C colours are the Slice 18 defaults (confirmed 2026-10-06); adjust here only.
BRAND: dict[str, tuple[str, str]] = {
    # Assurance de personnes (life)
    "MFC": ("Manuvie", "#1677c8"),
    "SLF": ("Sun Life", "#f4b400"),
    "GWO": ("Great-West Lifeco", "#d99800"),
    "IAG": ("iA Groupe financier", "#c54b8c"),
    # Assurance de dommages (P&C)
    "IFC": ("Intact Financial", "#1a4f8b"),
    "DFY": ("Definity Financial", "#00857a"),
    "AV": ("Aviva Canada", "#ffd200"),
    "TD": ("TD Insurance", "#008a00"),
}


def brand_name(company_id: str) -> str:
    entry = BRAND.get(company_id)
    return entry[0] if entry else company_id


def brand_colour(company_id: str) -> str:
    entry = BRAND.get(company_id)
    return entry[1] if entry else "#8ea0ac"


def format_value(value: Any, kind: str, metric_id: str | None = None) -> str:
    """Single value convention for both universes (Slice 18 decision 2).

    Amounts in CAD billions as `G$`, client-asset totals as `T$`, ratios and
    percentages to one decimal with `%`, per-share figures to two decimals.
    """
    if value is None:
        return "—"
    number = float(value)
    if kind == "per_share":
        return f"{number:,.2f} $"
    if kind == "billion":
        return f"{number:,.3f} G$"
    if kind == "assets":
        return f"{number:,.1f} T$" if metric_id == "total_client_assets" else f"{number:,.0f} G$"
    return f"{number:.1f} %"


def vigie_header(eyebrow: str, title: str, subtitle: str) -> str:
    """The branded page header, parameterised per universe."""
    return (
        "<header class='vigie-header'>"
        f"<p class='vigie-eyebrow'>{escape(eyebrow)}</p>"
        f"<h1>{escape(title)}</h1>"
        f"<p>{escape(subtitle)}</p>"
        "</header>"
    )


def row_open(company_id: str) -> str:
    return f"<tr style='--company-colour:{escape(brand_colour(company_id))}'>"


def row_header_cell(company_id: str, ticker: str | None = None) -> str:
    """Brand-coloured leading cell with the issuer name and an optional ticker."""
    ticker_html = f"<span class='comparison-ticker'>{escape(ticker)}</span>" if ticker else ""
    return f"<th scope='row'><strong>{escape(brand_name(company_id))}</strong>{ticker_html}</th>"


def period_chip(period: Any) -> str:
    return f"<span class='comparison-period'>{escape(str(period))}</span>" if period else ""


def delta_badge(text: str, tone: str, period_label: str | None = None) -> str:
    """A YoY delta chip. tone is one of up / down / flat; period_label is small print."""
    tone = tone if tone in {"up", "down", "flat"} else "flat"
    badge = f"<span class='comparison-delta {tone}'>{escape(text)}</span>" if text else ""
    label = f"<span class='comparison-delta-period'>{escape(period_label)}</span>" if period_label else ""
    return badge + label


def meta_cell(text: str) -> str:
    """A secondary descriptive cell (e.g. scope, calendar, closing date)."""
    return f"<td class='comparison-meta'>{escape(str(text))}</td>"


def value_cell(value_html: str, period: Any = None, delta_html: str = "") -> str:
    chip = period_chip(period)
    return f"<td><strong>{value_html}</strong>{chip}{delta_html}</td>"


def empty_cell(text: str = "N/A") -> str:
    return f"<td class='comparison-empty'>{escape(text)}</td>"


def table_shell(header_cells: list[str], body_rows: list[str]) -> str:
    """Wrap header cells and already-rendered rows in the shared branded table."""
    head = "".join(header_cells)
    body = "".join(body_rows)
    return (
        "<div class='comparison-wrap'><table class='comparison-table'><thead><tr>"
        f"{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def header_cell(label: str, help_text: str | None = None) -> str:
    title = f" title='{escape(help_text)}'" if help_text else ""
    return f"<th scope='col'{title}>{escape(label)}</th>"
