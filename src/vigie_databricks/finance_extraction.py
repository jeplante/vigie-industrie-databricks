"""Deterministic, source-specific financial KPI extraction."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
import re

from pypdf import PdfReader

from vigie_databricks.insurer_contract import InsurerContract


ALIASES = {
    "MFC": {"core_eps": ("core EPS", "BPA tire des activites de base"), "core_earnings": ("core earnings",), "net_income": ("net income attributed to shareholders",), "core_roe": ("core ROE",), "licat_ratio": ("LICAT ratio",)},
    "SLF": {"core_eps": ("underlying EPS", "underlying earnings per share"), "core_earnings": ("underlying net income",), "net_income": ("reported net income",), "core_roe": ("underlying ROE",), "licat_ratio": ("LICAT ratio",), "assets_under_management": ("assets under management",)},
    "GWO": {"core_eps": ("base EPS", "base earnings per common share", "base earnings per share"), "core_earnings": ("Lifeco base earnings", "base earnings"), "net_income": ("Lifeco net earnings - common shareholders", "net earnings"), "core_roe": ("consolidated base ROE", "base return on equity", "base ROE"), "licat_ratio": ("LICAT ratio",), "total_client_assets": ("total client assets", "total assets under administration (AUA)", "total assets under administration")},
    "IAG": {"core_eps": ("core EPS",), "core_earnings": ("core earnings",), "net_income": ("net income attributed to common shareholders",), "core_roe": ("core ROE",), "licat_ratio": ("solvency ratio", "LICAT ratio"), "assets_under_administration": ("assets under management and assets under administration", "assets under management and administration", "assets under administration")},
}
EXPECTED_METRICS = {company_id: frozenset(metrics) for company_id, metrics in ALIASES.items()}
NUMBER_PATTERN = r"\d{1,3}(?:[ ,]\d{3})+|\d+(?:[.,]\d+)?"
TABLE_NUMBER_PATTERN = r"\d{1,3}(?:,\d{3})+|\d+(?:[.,]\d+)?"
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
    # Some older PDF fonts split a three-digit percentage at the hundreds
    # position (for example ``1 29%``). Repair only this narrow OCR shape.
    text = re.sub(r"(?<!\d)1\s+([0-9]{2})\s*%", r"1\1%", text)
    extracted: list[ExtractedMetric] = []
    for metric_id, aliases in ALIASES[company_id].items():
        expected_unit = contract.metrics[metric_id].unit
        for alias in aliases:
            # PDF text extraction commonly renders reference markers inline
            # (for example ``Base EPS2 $1.42``). Consume those markers before
            # looking for the financial value so they cannot become the value.
            # Footnote references are attached to the label in extracted PDF
            # text (``Base EPS2``). Whitespace means the following number is a
            # value and must not be consumed as a reference.
            alias_with_reference = re.escape(alias) + r"(?:\d+(?:,\d+)*)?"
            table_pattern = re.compile(
                re.escape(alias)
                + rf".{{0,50}}?\((?:in\s+)?(?P<table_unit>\$|millions?|billions?|trillions?)\)"
                + rf"(?:\s*(?:\(\d+\)|[\u2020\u2021,*]+))*\s*(?:\d+\s+(?=\$))?\$?\s*(?P<table_number>{TABLE_NUMBER_PATTERN})",
                re.IGNORECASE,
            )
            table_match = table_pattern.search(text)
            if table_match:
                table_unit = table_match.group("table_unit").lower().rstrip("s")
                table_value = _normalized_value(table_match.group("table_number"), table_unit, expected_unit)
                if table_value is not None:
                    raw_match = table_match.group(0)
                    if metric_id != "core_earnings" or not re.search(r"per share|adjustments?", raw_match, re.IGNORECASE):
                        extracted.append(ExtractedMetric(metric_id, table_value, expected_unit, raw_match, raw_match[:500]))
                        break
            # Great-West Lifeco's Q4 releases present AUA in a financial-statement
            # table whose heading omits both the currency symbol and scale. Those
            # reports state the table in millions, so normalize its first value
            # only for this source-specific KPI rather than guessing elsewhere.
            if company_id == "GWO" and metric_id == "total_client_assets":
                gwo_aua_table = re.compile(
                    re.escape(alias) + r"(?:\d+(?:,\d+)*)?\s+(?P<table_number>\d{1,3}(?:,\d{3})+)",
                    re.IGNORECASE,
                ).search(text)
                if gwo_aua_table:
                    raw_match = gwo_aua_table.group(0)
                    table_value = _normalized_value(gwo_aua_table.group("table_number"), "million", expected_unit)
                    if table_value is not None:
                        extracted.append(ExtractedMetric(metric_id, table_value, expected_unit, raw_match, raw_match[:500]))
                        break
            alias_pattern = re.compile(alias_with_reference, re.IGNORECASE)
            found = False
            for alias_match in alias_pattern.finditer(text):
                window = text[alias_match.start():alias_match.end() + 180]
                for value_match in VALUE_PATTERN.finditer(window, alias_match.end() - alias_match.start()):
                    raw_match = window[:value_match.end()]
                    number = value_match.group("prefix_number") or value_match.group("suffix_number")
                    source_unit = value_match.group("prefix_scale") or value_match.group("prefix_currency") or value_match.group("suffix_unit")
                    numeric = float(number.replace(" ", "").replace(",", "")) if re.fullmatch(r"\d{1,3}(?:[ ,]\d{3})+", number) else float(number.replace(",", "."))
                    if metric_id == "core_earnings" and re.search(r"per share|adjustments?", raw_match, re.IGNORECASE):
                        break
                    if re.search(r"(?:increased|decreased|rose|fell|up|down)\s+(?:\w+\s+){0,3}by\s*$", raw_match[:value_match.start()], re.IGNORECASE):
                        continue
                    if (
                        expected_unit.startswith("CAD_")
                        and source_unit == "$"
                        and re.fullmatch(r"20\d{2}", number)
                        and re.search(r"year-to-date|quarter|20\d{2}", raw_match[:value_match.start()], re.IGNORECASE)
                    ):
                        continue
                    value = _normalized_value(number, source_unit, expected_unit)
                    if value is not None:
                        extracted.append(ExtractedMetric(metric_id, value, expected_unit, raw_match, raw_match[:500]))
                        found = True
                        break
                if found:
                    break
            if found:
                break
    return extracted


def extract_document_text(content: bytes, content_type: str, *, max_pages: int = 120, max_characters: int = 500_000,
                          pdf_extraction_mode: str = "plain") -> str:
    """Extract bounded text; PDF parsing is deterministic and never invokes AI."""
    if content_type == "application/pdf":
        if pdf_extraction_mode not in {"plain", "layout"}:
            raise ValueError("unsupported_pdf_extraction_mode")
        reader = PdfReader(BytesIO(content))
        parts = [(page.extract_text(extraction_mode=pdf_extraction_mode) or "")
                 for page in reader.pages[:max_pages]]
        return " ".join(parts)[:max_characters]
    if content_type in {"text/html", "application/xhtml+xml"}:
        return content.decode("utf-8", errors="replace")[:max_characters]
    raise ValueError("unsupported_document_content_type")


def infer_reporting_period(title: str) -> str | None:
    normalized = title.lower()
    compact_match = re.search(r"(?<!\d)(?:q([1-4])|(\d)q)(\d{2})(?!\d)", normalized)
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if compact_match:
        return f"20{compact_match.group(3)}-Q{compact_match.group(1) or compact_match.group(2)}"
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
    numeric = float(compact.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", compact)
                    else compact.replace(",", "."))
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
    if expected_unit == "CAD_TRILLION":
        if unit in {"trillion", "t$"}:
            return numeric
        if unit in {"billion", "g$"}:
            return numeric * 0.001
        if unit in {"million", "m$"}:
            return numeric * 0.000001
        if unit == "$" and numeric >= 1_000_000:
            return numeric * 0.000001
    return None
