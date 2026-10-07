"""Shared multi-insurer history chart, as a plain Vega-Lite specification.

Both universes draw the same chart: one line per issuer in its brand colour, a point per displayed
value with its official report in the tooltip (and as a link when one exists), zoom and pan. The
specification is a dictionary, so it is built and tested without a plotting library.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from shared_ui import brand_colour, brand_name


def _displayable(value: Any) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def history_spec(records: Iterable[dict[str, Any]], tooltips: Sequence[tuple[str, str]] = ()) -> dict[str, Any]:
    """Records carry company_id, period_id, display_value and optionally source_url plus extra tooltip fields.

    ``tooltips`` adds (field, title) pairs shown on hover, for example a closing date or a calendar basis.
    A missing value breaks the line rather than being interpolated across.
    """
    rows = [dict(record) for record in records]
    for row in rows:
        row["display_value"] = float(row["display_value"]) if _displayable(row.get("display_value")) else None
        row["issuer"] = brand_name(row["company_id"])
    companies = sorted({row["company_id"] for row in rows})
    colour = {"field": "issuer", "type": "nominal", "title": "Assureur",
              "scale": {"domain": [brand_name(company) for company in companies],
                        "range": [brand_colour(company) for company in companies]}}
    x = {"field": "period_id", "type": "ordinal", "title": "Période", "sort": "ascending"}
    y = {"field": "display_value", "type": "quantitative", "title": "Valeur"}
    tooltip = [{"field": "issuer", "title": "Assureur"}, {"field": "period_id", "title": "Période"},
               {"field": "display_value", "title": "Valeur", "format": ",.3f"}]
    tooltip += [{"field": field, "title": title} for field, title in tooltips]
    tooltip.append({"field": "source_url", "title": "Rapport officiel"})
    return {
        "data": {"values": rows},
        "layer": [
            {"mark": {"type": "line"}, "encoding": {"x": x, "y": y, "color": colour}},
            {"mark": {"type": "circle", "size": 60},
             "transform": [{"filter": "datum.display_value != null"}],
             "encoding": {"x": x, "y": y, "color": colour, "tooltip": tooltip, "href": {"field": "source_url"}},
             "params": [{"name": "zoom", "select": "interval", "bind": "scales"}]},
        ],
    }
