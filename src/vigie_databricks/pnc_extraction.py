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
        "net_income": ("net income attributable to common shareholders",
                       "net (loss) income attributable to common shareholders",
                       "net income (loss) attributable to common shareholders"),
        "operating_roe": ("operating ROE",),
    },
    "AV": {
        "insurance_revenue": ("Canada insurance revenue",),
        "combined_ratio": ("Canada combined operating ratio", "Canada combined ratio"),
        "operating_income": ("Canada operating profit",),
    },
    "TD": {
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
        r"(?P<quarter>Q[1-4]-20\d{2})[.\s]+Q[1-4]-20\d{2}"
        r"(?:[.\s]+Restated(?:[.\s]+\d+)?)?[.\s]+Change"
        r"(?P<body>.*?)Per share measures",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return None
    label = (r"Combined\s+ratio(?:\s*\(undiscounted\))?"
             if metric_id == "combined_ratio" else re.escape(row_label))
    match = re.search(r"(?<!\w)(?P<label>" + label + r")"
                      r"\s*(?:\.\s*)?(?:[1-4](?:\s*,\s*[1-4])*\s+)?"
                      r"(?P<number>\d[\d,]*(?:\.\d+)?)(?=\s|\.)",
                      section.group("body"), re.IGNORECASE)
    if not match:
        return None
    source_unit = "%" if expected_unit == "PERCENT" else "million"
    value = _normalized_value(match.group("number"), source_unit, expected_unit)
    if value is None:
        return None
    context = (f"Consolidated Highlights {section.group('quarter')} "
               f"{match.group('label')} {match.group('number')}"
               f"{'%' if source_unit == '%' else ' million CAD'}")
    return ExtractedMetric(metric_id, value, expected_unit, match.group("number"), context)


def _comparative_quarter_metric(
    company_id: str, text: str, metric_id: str, expected_unit: str, target_period: str
) -> ExtractedMetric | None:
    """Read only an explicitly restated prior-quarter column in an issuer table."""
    if company_id == "IFC":
        section = re.search(
            r"Consolidated Highlights\s*\.?\s*"
            r"\(in millions of Canadian dollars except as otherwise noted\)\s*\.?\s*"
            r"(?P<current>Q[1-4]-20\d{2})[.\s]+(?P<prior>Q[1-4]-20\d{2})"
            r"(?P<restated>[.\s]+Restated(?:[.\s]+\d+)?)?[.\s]+Change"
            r"(?P<body>.*?)Per share measures",
            text, re.IGNORECASE | re.DOTALL,
        )
        labels = {
            "combined_ratio": r"Combined\s+ratio\s*\(undiscounted\)",
            "operating_income": r"Net operating income attributable to common shareholders",
            "net_income": r"Net income",
        }
        footnote = r"(?:[1-4](?:\s*,\s*[1-4])*\s+)?"
    elif company_id == "DFY":
        section = re.search(
            r"Consolidated Results\s*\.?\s*"
            r"\(in millions of dollars, except as otherwise noted\)\s*\.?\s*"
            r"(?P<current>Q[1-4] 20\d{2})\s+(?P<prior>Q[1-4] 20\d{2})"
            r"(?P<restated>\s*\.?\s*\(Restated\))?\s+Change"
            r"(?P<body>.*?)Per share measures",
            text, re.IGNORECASE | re.DOTALL,
        )
        labels = {
            "insurance_revenue": r"Insurance revenue",
            "combined_ratio": r"Combined ratio",
            "claims_ratio": r"Claims ratio",
            "expense_ratio": r"Expense ratio",
            "operating_income": r"Operating net income",
            "net_income": (
                r"Net\s+(?:\(loss\)\s+)?income(?:\s+\(loss\))?"
                r"\s+attributable to common shareholders"
            ),
        }
        footnote = ""
    else:
        return None
    if not section or not section.group("restated") or metric_id not in labels:
        return None
    prior = section.group("prior")
    if f"{prior[-4:]}-Q{prior[1]}" != target_period:
        return None
    match = re.search(
        r"(?<!\w)(?P<label>" + labels[metric_id] + r")\s+" + footnote
        + r"(?P<current_value>\(?\d[\d,]*(?:\.\d+)?\)?)\s*%?\s+"
        + r"(?P<prior_value>\(?\d[\d,]*(?:\.\d+)?\)?)\s*%?",
        section.group("body"), re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group("prior_value")
    negative = raw.startswith("(") and raw.endswith(")")
    source_unit = "%" if expected_unit == "PERCENT" else "million"
    value = _normalized_value(raw[1:-1] if negative else raw, source_unit, expected_unit)
    if value is None:
        return None
    if negative:
        value = -value
    context = (f"Restated comparative quarter {prior} {match.group('label')} "
               f"{raw}{'%' if source_unit == '%' else ' million CAD'}")
    return ExtractedMetric(metric_id, value, expected_unit, raw, context)


def _reported_current_period(company_id: str, text: str) -> str | None:
    if company_id == "IFC":
        pattern = r"Consolidated Highlights.*?\b(Q[1-4]-20\d{2})\b"
    elif company_id == "DFY":
        pattern = r"Consolidated Results.*?\b(Q[1-4] 20\d{2})\b"
    elif company_id == "TD":
        match = re.search(r"Quarterly comparison\s*.\s*(Q[1-4])\s+(20\d{2})\s+vs", text,
                          re.IGNORECASE | re.DOTALL)
        return f"{match.group(2)}-{match.group(1)}" if match else None
    else:
        return None
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    quarter = re.search(r"Q([1-4])[- ](20\d{2})", match.group(1), re.IGNORECASE)
    return f"{quarter.group(2)}-Q{quarter.group(1)}" if quarter else None


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


def _following_period(period_id: str, quarters: int) -> str:
    year, quarter = int(period_id[:4]), int(period_id[-1]) + quarters
    return f"{year + (quarter - 1) // 4}-Q{(quarter - 1) % 4 + 1}"


def _td_earlier_insurance_income(text: str, expected_unit: str, target_period: str) -> ExtractedMetric | None:
    """TD's standalone Insurance net income for ``target_period``, from a later report's comparison.

    TD's reports before 2025 give only the combined Wealth Management and Insurance segment. From 2025 each
    comparison states the standalone figure and its change: "Insurance net income of $168 million, a decrease
    of $32 million, ... compared with the first quarter last year", or "an increase of $267 million, compared
    with a loss of $99 million in the prior quarter". A value written in the sentence ($99 million loss) is
    used as such; otherwise the earlier value is the figure minus the stated change, an exact difference of
    two published numbers. Only the same quarter of the previous year or the previous quarter is read.
    """
    comparisons = re.finditer(
        r"Quarterly comparison\s*.\s*(?P<quarter>Q[1-4])\s+(?P<year>20\d{2})\s+vs\s*.?\s*(?P<prior_quarter>Q[1-4])\s+(?P<prior_year>20\d{2})"
        r"(?P<body>.*?)(?=Quarterly comparison|TABLE\s+\d+:|$)",
        text, re.IGNORECASE | re.DOTALL,
    )
    for comparison in comparisons:
        current_period = f"{comparison.group('year')}-{comparison.group('quarter').upper()}"
        prior = f"{comparison.group('prior_year')}-{comparison.group('prior_quarter').upper()}"
        if prior != target_period or current_period not in (_following_period(prior, 4), _following_period(prior, 1)):
            continue
        match = re.search(
            r"and Insurance net income of\s*\$(?P<number>[\d,]+)\s*million\s*,?\s*an?\s+(?P<direction>increase|decrease)"
            r"\s+of\s*\$(?P<change>[\d,]+)\s*million(?:\s*,\s*or\s*[\d.]+\s*%)?\s*,?\s*compared with\s+"
            r"(?:(?:a|net)\s+(?:net\s+)?(?P<kind>loss|income)\s+of\s*\$(?P<stated>[\d,]+)\s*million\s+in\s+)?"
            r"the (?:prior quarter|(?:first|second|third|fourth) quarter last year)",
            comparison.group("body"), re.IGNORECASE | re.DOTALL,
        )
        if not match:
            continue
        current = _normalized_value(match.group("number"), "million", expected_unit)
        change = _normalized_value(match.group("change"), "million", expected_unit)
        if current is None or change is None:
            continue
        derived = round(current - change if match.group("direction").lower() == "increase" else current + change, 6)
        if match.group("stated"):
            stated = _normalized_value(match.group("stated"), "million", expected_unit)
            value = -stated if match.group("kind").lower() == "loss" else stated
            if abs(value - derived) > 1e-9:  # the sentence contradicts itself: read nothing
                continue
            how = f"stated in the {current_period[-2:]} comparison as {'a loss' if value < 0 else 'income'} of ${match.group('stated')} million"
        else:
            value = derived
            how = (f"derived from a later comparison: ${match.group('number')} million, {match.group('direction').lower()} of "
                   f"${match.group('change')} million")
        how = how.replace(current_period[-2:] + " comparison", "next quarter's comparison")
        millions = round(value * 1000)
        context = f"{target_period[-2:]} {target_period[:4]} Insurance net income of {millions} million CAD, {how}"
        return ExtractedMetric("net_income", value, expected_unit, str(millions), context)
    return None


def _dfy_quarterly_insurance_revenue(text: str, expected_unit: str) -> ExtractedMetric | None:
    """Read only the current-quarter insurance revenue in Definity's CAD-millions table."""
    section = re.search(
        r"Consolidated Results\s*\.?\s*"
        r"\(in millions of dollars, except as otherwise noted\)\s*\.?\s*"
        r"(?P<quarter>Q[1-4] 20\d{2})\s+Q[1-4] 20\d{2}"
        r"(?:\s*\.?\s*\(Restated\))?\s+Change"
        r"(?P<body>.*?)Per share measures",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return None
    match = re.search(r"(?:^|\.\s+)Insurance revenue\s+(?P<number>\d[\d,]*\.\d+)(?=\s)",
                      section.group("body"), re.IGNORECASE)
    if not match:
        return None
    value = _normalized_value(match.group("number"), "million", expected_unit)
    if value is None:
        return None
    context = f"Consolidated Results {section.group('quarter')} Insurance revenue {match.group('number')} million CAD"
    return ExtractedMetric("insurance_revenue", value, expected_unit, match.group("number"), context)


def _dfy_quarterly_net_income(text: str, expected_unit: str) -> ExtractedMetric | None:
    """Read the current quarterly table column, including parenthesized losses."""
    section = re.search(
        r"Consolidated Results\s*\.?\s*"
        r"\(in millions of dollars, except as otherwise noted\)\s*\.?\s*"
        r"(?P<quarter>Q[1-4] 20\d{2})\s+Q[1-4] 20\d{2}"
        r"(?:\s*\.?\s*\(Restated\))?\s+Change"
        r"(?P<body>.*?)Per share measures",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not section:
        return None
    match = re.search(
        r"(?:^|\.\s+)(?P<label>Net\s+(?:\(loss\)\s+)?income(?:\s+\(loss\))?"
        r"\s+attributable to common shareholders)\s+"
        r"(?P<number>\(?\d[\d,]*(?:\.\d+)?\)?)",
        section.group("body"), re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group("number")
    negative = raw.startswith("(") and raw.endswith(")")
    value = _normalized_value(raw[1:-1] if negative else raw, "million", expected_unit)
    if value is None:
        return None
    if negative:
        value = -value
    context = (f"Consolidated Results {section.group('quarter')} "
               f"{match.group('label')} {raw} million CAD")
    return ExtractedMetric("net_income", value, expected_unit, raw, context)


def _aviva_canada_quarterly_cor(
    text: str, expected_unit: str, target_period: str | None
) -> ExtractedMetric | None:
    """Select the current Canada undiscounted COR from Aviva's quarterly table."""
    header = re.search(
        r"Discounted COR\s+Undiscounted COR\s+"
        r"Q(?P<quarter>[1-4])(?P<year>\d{2})\s+Q[1-4]\d{2}\s+Change\s+"
        r"Q[1-4]\d{2}\s+Q[1-4]\d{2}\s+Change",
        text, re.IGNORECASE,
    )
    if not header:
        return None
    reported_period = f"20{header.group('year')}-Q{header.group('quarter')}"
    if target_period and reported_period != target_period:
        return None
    section = re.split(
        r"Discounted COR\s+Undiscounted COR", text[header.end():],
        maxsplit=1, flags=re.IGNORECASE,
    )[0]
    total = re.search(r"\bTotal\s+\d{2,3}\.\d+\s*%", section, re.IGNORECASE)
    if not total:
        return None
    table_body = section[:total.start()]
    match = re.search(
        r"(?:^|\s)Canada\s+"
        r"\d{2,3}\.\d+\s*%\s+\d{2,3}\.\d+\s*%\s+"
        r"(?:\(\s*\d+(?:\.\d+)?\s*\)|[-+]?\d+(?:\.\d+)?)\s*pp\s+"
        r"(?P<undiscounted>\d{2,3}\.\d+)\s*%\s+"
        r"\d{2,3}\.\d+\s*%\s+"
        r"(?:\(\s*\d+(?:\.\d+)?\s*\)|[-+]?\d+(?:\.\d+)?)\s*pp",
        table_body, re.IGNORECASE,
    )
    if not match:
        return None
    raw = match.group("undiscounted")
    value = _normalized_value(raw, "%", expected_unit)
    if value is None:
        return None
    context = f"Canada combined operating ratio (undiscounted COR) {raw}% {reported_period}"
    return ExtractedMetric("combined_ratio", value, expected_unit, raw, context)


def extract_pnc_metrics(
    company_id: str, content: str, contract: InsurerContract, *, target_period: str | None = None
) -> list[ExtractedMetric]:
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
        if target_period and company_id in {"IFC", "DFY"}:
            comparative = _comparative_quarter_metric(
                company_id, text, metric_id, expected_unit, target_period
            )
            if comparative is not None:
                extracted.append(comparative)
                continue
            if _reported_current_period(company_id, text) != target_period:
                continue
        if target_period and company_id == "TD" and _reported_current_period(company_id, text) not in {None, target_period}:
            # a report one quarter or one year later still gives this quarter's standalone Insurance net income
            reported = _reported_current_period(company_id, text)
            if metric_id == "net_income" and reported in (_following_period(target_period, 4), _following_period(target_period, 1)):
                derived = _td_earlier_insurance_income(text, expected_unit, target_period)
                if derived is not None:
                    extracted.append(derived)
            continue
        if company_id == "AV" and metric_id == "combined_ratio":
            canada_cor = _aviva_canada_quarterly_cor(text, expected_unit, target_period)
            if canada_cor is not None:
                extracted.append(canada_cor)
            continue
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
        if company_id == "IFC" and metric_id in {"claims_ratio", "expense_ratio"}:
            # These components reconcile to the discounted ratio, while the
            # comparable P&C combined ratio uses the undiscounted basis.
            continue
        if company_id == "TD" and metric_id == "net_income":
            insurance_income = _td_quarterly_insurance_income(text, expected_unit)
            if insurance_income is not None:
                extracted.append(insurance_income)
                continue
        if company_id == "DFY" and metric_id == "insurance_revenue":
            revenue = _dfy_quarterly_insurance_revenue(text, expected_unit)
            if revenue is not None:
                extracted.append(revenue)
            # Prose can describe YTD or group premiums; require the table.
            continue
        if company_id == "DFY" and metric_id == "net_income":
            net_income = _dfy_quarterly_net_income(text, expected_unit)
            if net_income is not None:
                extracted.append(net_income)
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
