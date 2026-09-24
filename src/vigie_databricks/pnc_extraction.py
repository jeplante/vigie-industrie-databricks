"""Deterministic candidate extraction for the isolated Canadian P&C domain."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from vigie_databricks.finance_extraction import ExtractedMetric, _normalized_value
from vigie_databricks.insurer_contract import InsurerContract


PNC_ALIASES = {
    "IFC": {
        "insurance_revenue": ("insurance revenue",),
        "combined_ratio": ("combined ratio",),
        "claims_ratio": ("claims ratio",),
        "expense_ratio": ("expense ratio",),
        "catastrophe_losses": ("catastrophe losses", "catastrophe loss"),
        "operating_income": ("operating net income", "net operating income"),
        "net_income": ("net income",),
        "operating_roe": ("operating ROE",),
    },
    "DFY": {
        "insurance_revenue": ("insurance revenue",),
        "combined_ratio": ("combined ratio",),
        "claims_ratio": ("claims ratio",),
        "expense_ratio": ("expense ratio",),
        "catastrophe_losses": ("catastrophe losses",),
        "operating_income": ("operating net income",),
        "net_income": ("net income attributable to common shareholders",),
        "operating_roe": ("operating ROE",),
    },
    "AV": {
        "insurance_revenue": ("Canada insurance revenue",),
        "combined_ratio": ("Canada combined operating ratio", "Canada combined ratio"),
        "operating_income": ("Canada operating profit",),
    },
    "TD": {
        "catastrophe_losses": ("catastrophe claims",),
        "net_income": ("Insurance net income",),
        "operating_roe": ("Return on common equity – Insurance",),
    },
}

_NUMBER = r"\d{1,3}(?:[, ]\d{3})+|\d+(?:[.,]\d+)?"
_VALUE = re.compile(rf"(?P<number>{_NUMBER})\s*(?P<unit>%|million|billion|\$)", re.IGNORECASE)
_DIRECT_VALUE = re.compile(
    rf"\s*(?:(?:was|is|of|:|=)\s*)?(?:CAD\s*|C\$\s*|\$\s*)?"
    rf"(?P<number>{_NUMBER})\s*(?P<unit>%|million\b|billion\b)",
    re.IGNORECASE,
)


class _ReportText(HTMLParser):
    """Read visible report text, excluding metadata, scripts and footnotes."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style", "sup"}:
            self.hidden.append(tag)
        elif not self.hidden and tag in {"p", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append(". ")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _ifc_quarterly_highlight(
    text: str, metric_id: str, row_label: str, expected_unit: str
) -> ExtractedMetric | None:
    """Read a named current-quarter column from IFC's consolidated highlights."""
    section = re.search(
        r"Consolidated Highlights\s*\.?\s*"
        r"\(in millions of Canadian dollars except as otherwise noted\)\s*\.?\s*"
        r"(?P<quarter>Q[1-4]-20\d{2})[.\s]+Q[1-4]-20\d{2}[.\s]+Change"
        r"(?P<body>.*?)Per share measures",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return None
    match = re.search(r"(?<!\w)" + re.escape(row_label) +
                      r"\s*(?:\.\s*)?(?:1\s+)?(?P<number>\d[\d,]*(?:\.\d+)?)(?=\s|\.)",
                      section.group("body"), re.IGNORECASE)
    if not match:
        return None
    source_unit = "%" if expected_unit == "PERCENT" else "million"
    value = _normalized_value(match.group("number"), source_unit, expected_unit)
    if value is None:
        return None
    context = (f"Consolidated Highlights {section.group('quarter')} "
               f"{row_label} {match.group('number')}"
               f"{'%' if source_unit == '%' else ' million CAD'}")
    return ExtractedMetric(metric_id, value, expected_unit, match.group("number"), context)


def _td_quarterly_insurance_income(text: str, expected_unit: str) -> ExtractedMetric | None:
    """Use only TD's standalone Insurance component in a quarterly comparison."""
    comparisons = re.finditer(
        r"Quarterly comparison\s*.\s*(Q[1-4])\s+(20\d{2})\s+vs\s*.?\s*Q[1-4]\s+20\d{2}"
        r"(?P<body>.*?)(?=Quarterly comparison|TABLE\s+\d+:|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    for comparison in comparisons:
        match = re.search(
            r"Wealth Management and Insurance net income for the quarter was\s*\$[\d,]+\s*million"
            r".{0,350}?Wealth Management net income of\s*\$[\d,]+\s*million"
            r".{0,250}?and Insurance net income of\s*\$(?P<number>[\d,]+)\s*million",
            comparison.group("body"), re.IGNORECASE | re.DOTALL,
        )
        if match:
            value = _normalized_value(match.group("number"), "million", expected_unit)
            if value is not None:
                context = (f"Quarterly comparison {comparison.group(1)} {comparison.group(2)} "
                           f"Insurance net income of ${match.group('number')} million")
                return ExtractedMetric("net_income", value, expected_unit, match.group("number"), context)
    return None


def extract_pnc_metrics(company_id: str, content: str, contract: InsurerContract) -> list[ExtractedMetric]:
    """Extract only explicitly labelled P&C candidates from an issuer's report."""
    if company_id not in PNC_ALIASES or company_id not in contract.companies:
        raise ValueError("company_id has no configured P&C extractor")
    parser = _ReportText()
    parser.feed(content)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    extracted: list[ExtractedMetric] = []
    for metric_id, aliases in PNC_ALIASES[company_id].items():
        if metric_id not in contract.metrics:
            continue
        expected_unit = contract.metrics[metric_id].unit
        if company_id == "IFC" and metric_id in {"net_income", "operating_income", "combined_ratio"}:
            row_label = {"net_income": "Net income",
                         "operating_income": "Net operating income attributable to common shareholders",
                         "combined_ratio": "Combined Ratio"}[metric_id]
            table_value = _ifc_quarterly_highlight(text, metric_id, row_label, expected_unit)
            if table_value is not None:
                extracted.append(table_value)
                continue
            if metric_id == "combined_ratio":
                # Narrative ratios can refer to Canada, a product line or a
                # foreign segment. Never infer consolidated scope from them.
                continue
        if company_id == "TD" and metric_id == "net_income":
            insurance_income = _td_quarterly_insurance_income(text, expected_unit)
            if insurance_income is not None:
                extracted.append(insurance_income)
                continue
        for alias in aliases:
            for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text, re.IGNORECASE):
                # TD's combined Wealth Management and Insurance segment is not
                # a comparable P&C value; accept only the standalone Insurance line.
                preceding = text[:match.start()].rsplit(".", 1)[-1].lower()
                if re.search(r"year[ -]to[ -]date|\bytd\b|six.month|twelve.month|full.year", preceding):
                    continue
                if company_id == "TD" and metric_id == "net_income" and "wealth management" in preceding:
                    continue
                if metric_id == "net_income" and re.search(r"operating\s*$", preceding):
                    continue
                value_match = _DIRECT_VALUE.match(text[match.end():])
                if not value_match:
                    continue
                context = text[match.start():match.end() + value_match.end()]
                value = _normalized_value(value_match.group("number"), value_match.group("unit"), expected_unit)
                if value is not None:
                    extracted.append(ExtractedMetric(metric_id, value, expected_unit, value_match.group(0), context))
                    break
            else:
                continue
            break
    return extracted
