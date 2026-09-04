"""Deterministic, source-specific financial KPI extraction."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re

from vigie_databricks.insurer_contract import InsurerContract


ALIASES = {
    "MFC": {"core_eps": ("core EPS", "BPA tire des activites de base"), "core_earnings": ("core earnings",), "net_income": ("net income attributed to shareholders",), "core_roe": ("core ROE",), "licat_ratio": ("LICAT ratio",)},
    "SLF": {"core_eps": ("underlying EPS",), "core_earnings": ("underlying net income",), "net_income": ("reported net income",), "core_roe": ("underlying ROE",), "licat_ratio": ("LICAT ratio",), "assets_under_management": ("assets under management",)},
    "GWO": {"core_eps": ("base EPS", "base earnings per share"), "core_earnings": ("base earnings",), "net_income": ("net earnings",), "core_roe": ("consolidated base ROE", "base ROE"), "licat_ratio": ("LICAT ratio",), "total_client_assets": ("total client assets",)},
    "IAG": {"core_eps": ("core EPS",), "core_earnings": ("core earnings",), "net_income": ("net income attributed to common shareholders",), "core_roe": ("core ROE",), "licat_ratio": ("solvency ratio", "LICAT ratio"), "assets_under_administration": ("assets under administration",)},
}
NUMBER_PATTERN = r"\d{1,3}(?:[ ,]\d{3})+|\d+(?:[.,]\d+)?"
VALUE_PATTERN = re.compile(
    rf"(?:(?P<prefix_currency>\$)\s*(?P<prefix_number>{NUMBER_PATTERN})(?:\s*(?P<prefix_scale>trillion|billion|million))?|(?P<suffix_number>{NUMBER_PATTERN})\s*(?P<suffix_unit>trillion|billion|million|T\$|G\$|M\$|\$|%))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedMetric:
    metric_id: str
    value: float
    unit: str
    raw_value: str
    context: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def extract_finance_metrics(company_id: str, content: str, contract: InsurerContract) -> list[ExtractedMetric]:
    if company_id not in ALIASES or company_id not in contract.companies:
        raise ValueError("company_id has no configured extractor")
    parser = _TextExtractor(); parser.feed(content)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    extracted: list[ExtractedMetric] = []
    for metric_id, aliases in ALIASES[company_id].items():
        expected_unit = contract.metrics[metric_id].unit
        for alias in aliases:
            match = re.search(re.escape(alias) + r".{0,100}?" + VALUE_PATTERN.pattern, text, re.IGNORECASE)
            if not match:
                continue
            number = match.group("prefix_number") or match.group("suffix_number")
            source_unit = match.group("prefix_scale") or match.group("prefix_currency") or match.group("suffix_unit")
            value = _normalized_value(number, source_unit, expected_unit)
            if value is not None:
                extracted.append(ExtractedMetric(metric_id, value, expected_unit, match.group(0), match.group(0)[:500]))
                break
    return extracted


def infer_reporting_period(title: str) -> str | None:
    normalized = title.lower()
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if not year_match:
        return None
    year = year_match.group(1)
    quarter_match = re.search(r"\b(?:q|t)([1-4])\b|\b([1-4])(st|nd|rd|th) quarter\b", normalized)
    if quarter_match:
        return f"{year}-Q{quarter_match.group(1) or quarter_match.group(2)}"
    for number, label in enumerate(("first", "second", "third", "fourth"), start=1):
        if f"{label} quarter" in normalized:
            return f"{year}-Q{number}"
    if re.search(r"\b(full year|annual|annuel)\b", normalized):
        return f"{year}-AN"
    return None


def _normalized_value(number: str, source_unit: str, expected_unit: str) -> float | None:
    compact = number.replace(" ", "")
    numeric = float(compact.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", compact) else compact.replace(",", "."))
    unit = source_unit.lower()
    if expected_unit == "PERCENT" and unit == "%":
        return numeric
    if expected_unit == "CAD_PER_SHARE" and unit == "$":
        return numeric
    if expected_unit == "CAD_BILLION" and unit == "$" and numeric >= 100:
        return numeric * 0.001
    factors = {"million": 0.001, "m$": 0.001, "billion": 1.0, "g$": 1.0, "trillion": 1000.0, "t$": 1000.0}
    if expected_unit == "CAD_BILLION" and unit in factors:
        return numeric * factors[unit]
    if expected_unit == "CAD_MILLION" and unit in {"million", "m$"}:
        return numeric
    if expected_unit == "CAD_TRILLION" and unit in {"trillion", "t$"}:
        return numeric
    return None