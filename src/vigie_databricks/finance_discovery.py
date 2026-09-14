"""Configuration-driven discovery of approved financial report links."""

from __future__ import annotations

from dataclasses import dataclass
import html as html_module
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse

from vigie_databricks.insurer_contract import FinancialSource


QUARTERLY_PATTERN = re.compile(r"\b(q[1-4](?:\d{2})?|[1-4]q\d{2}|quarter|quarterly|trimestre)\b", re.IGNORECASE)
ANNUAL_PATTERN = re.compile(r"\b(annual|year[ -]?end|annuel)\b", re.IGNORECASE)
NON_FINANCIAL_REPORT_PATTERN = re.compile(
    r"\b(transcript|webcast|conference call|presentation|slide deck|certificat(?:e|ion)|"
    r"dividend|fact sheet|annual information form|management discussion and analysis|mda|ifrs[ -]?17|"
    r"ncib|normal course issuer bid|supplemental information package|sip)\b",
    re.IGNORECASE,
)


def financial_document_preference(value: str) -> int:
    """Rank source-of-record documents; negative values must never be extracted."""
    material = re.sub(r"[-_/]+", " ", value.lower())
    if NON_FINANCIAL_REPORT_PATTERN.search(material):
        return -1
    if re.search(r"report to shareholders|shareholders? report|shrpt|mfc sr|mfc qpr", material):
        return 4
    if re.search(r"quarterly report|financial report", material):
        return 3
    if re.search(r"earnings release|\bearnings\b|financial results|news release", material):
        return 2
    if re.search(r"financial statements", material):
        return 1
    return 0


@dataclass(frozen=True)
class DiscoveredFinancialDocument:
    document_type: str
    source_url: str
    title: str


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text)))
        if tag.lower() == "a":
            self._href = None
            self._text = []


def discover_financial_documents(html: str, source: FinancialSource) -> list[DiscoveredFinancialDocument]:
    collector = _LinkCollector()
    collector.feed(html)
    decoded = html_module.unescape(html)
    embedded = [
        (match.group("href"), match.group("title"))
        for match in re.finditer(
            r'"title"\s*:\s*"(?P<title>[^"]+)"\s*,\s*"href"\s*:\s*"(?P<href>[^"]+)"',
            decoded,
            re.IGNORECASE,
        )
    ]
    documents: dict[tuple[str, str], DiscoveredFinancialDocument] = {}
    for href, text in [*collector.links, *embedded]:
        url = urljoin(source.url, href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in source.allowed_hosts:
            continue
        if not parsed.path.lower().endswith(".pdf"):
            continue
        material = f"{text} {parsed.path}"
        document_type = _document_type(material)
        if document_type and document_type in source.document_types:
            title = re.sub(r"\s+", " ", text).strip()
            documents[(document_type, url)] = DiscoveredFinancialDocument(document_type, url, title)
    return [documents[key] for key in sorted(documents)]


def _document_type(value: str) -> str | None:
    # Transcripts, presentations, and compliance certificates are official
    # investor-relations documents, but not suitable as the deterministic
    # source of record for KPI extraction.
    if financial_document_preference(value) < 0:
        return None
    if QUARTERLY_PATTERN.search(value):
        return "quarterly_report"
    if ANNUAL_PATTERN.search(value):
        return "annual_report"
    return None
