"""Aviva Canada half-year and full-year combined operating ratio, from Aviva Canada's own media statements.

Aviva Canada publishes no isolated Canadian quarter, so the quarterly comparison shows it N/A. Its media
statements on aviva.ca ("Aviva Canada posts half-year 2026 results") give the Canadian combined operating
ratio (undiscounted) for the half-year and the full year. Those values are published with their own
validation status (``validated_semiannual``, ``validated_annual``) and period labels (``2026-H1``,
``2025-FY``): everything that reads quarters (``validated_quarterly``) ignores them, and the App shows them
apart, never compared with a quarter.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
import hashlib
import html
import json
import re
from typing import Any, Callable, Iterable

from vigie_databricks.operations_monitor import PNC_RATIO_BOUNDS

HOSTS = ("www.aviva.ca", "aviva.ca")
TITLE = re.compile(r"aviva canada posts (?P<kind>half|full)-year (?:results )?(?P<year>20\d\d)(?: results)?", re.I)
# "achieving a HY26 Combined Operating Ratio (COR*) of 93.0%", "Our FY25 Combined Operating Ratio (COR*) of 95.6%",
# "For HY25, Aviva Canada ... achieving a Combined Operating Ratio (COR*) of 94.7%"
RATIO = re.compile(r"(?:(?P<label>HY|FY)(?P<yy>\d\d)\s+)?Combined Operating Ratio\s*\(COR\*?\)\s+of\s+(?P<value>\d{2,3}(?:\.\d)?)\s?%", re.I)
LEAD_LABEL = re.compile(r"\bFor\s+(?P<label>HY|FY)(?P<yy>\d\d)\b", re.I)
UNDISCOUNTED = re.compile(r"COR results cited are on an undiscounted basis", re.I)
STATUS = {"H1": "validated_semiannual", "FY": "validated_annual"}


def statement_text(page: str) -> str:
    """Visible text of an aviva.ca media statement page."""
    page = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def period_of(title: str) -> str | None:
    """'2026-H1' for "Aviva Canada posts half-year 2026 results", '2025-FY' for the full year, else None."""
    match = TITLE.search(title or "")
    if not match:
        return None
    return f"{match.group('year')}-{'H1' if match.group('kind').lower() == 'half' else 'FY'}"


def period_end(period_id: str) -> date:
    return date(int(period_id[:4]), 6, 30) if period_id.endswith("H1") else date(int(period_id[:4]), 12, 31)


def extract_ratio(text: str, period_id: str) -> tuple[float | None, str | None, str]:
    """(value, rejection reason, excerpt). The ratio's own label (HY26, FY25) must name the expected period,
    the statement must say the ratio is undiscounted, and the value must be plausible."""
    if not UNDISCOUNTED.search(text):
        return None, "undiscounted_basis_not_stated", ""
    match = RATIO.search(text)
    if not match:
        return None, "combined_operating_ratio_not_found", ""
    excerpt = text[max(0, match.start() - 120):match.end() + 20]
    label = match if match.group("label") else LEAD_LABEL.search(text[:match.start()])
    if not label:
        return None, "ratio_period_label_missing", excerpt
    named = f"20{label.group('yy')}-{'H1' if label.group('label').upper() == 'HY' else 'FY'}"
    if named != period_id:
        return None, f"ratio_period_mismatch ({named} vs {period_id})", excerpt
    value = float(match.group("value"))
    low, high = PNC_RATIO_BOUNDS["combined_ratio"]
    if not low <= value <= high:
        return None, f"ratio_out_of_bounds ({value})", excerpt
    return value, None, excerpt


def discover_statements(news_rows: Iterable[dict[str, Any]], published_periods: Iterable[str]) -> list[tuple[str, str]]:
    """(period_id, url) of Aviva Canada results statements not yet published, oldest first."""
    published = set(published_periods)
    found = {}
    for article in news_rows:
        if article.get("company_id") != "AV":
            continue
        period = period_of(str(article.get("title") or ""))
        url = str(article.get("source_url") or "")
        if period and period not in published and re.match(r"https://(?:www\.)?aviva\.ca/", url):
            found.setdefault(period, url)
    return sorted(found.items())


def build_rows(
    statements: Iterable[tuple[str, str]],
    fetch: Callable[[str, Iterable[str]], str],
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(rows for pnc_gold_observations, one decision per statement). A failed read or check is a rejection."""
    now = now or datetime.now(UTC)
    rows, decisions = [], []
    for period, url in statements:
        try:
            page = fetch(url, HOSTS)
        except Exception as error:  # one unreadable page must not hide the others
            decisions.append({"period_id": period, "url": url, "decision": "rejected", "reason": f"fetch_failed: {type(error).__name__}"})
            continue
        value, reason, excerpt = extract_ratio(statement_text(page), period)
        if reason:
            decisions.append({"period_id": period, "url": url, "decision": "rejected", "reason": reason})
            continue
        digest = hashlib.sha256(page.encode("utf-8")).hexdigest()
        evidence = {"company_id": "AV", "period_id": period, "period_end": period_end(period).isoformat(),
                    "calendar_basis": "calendar", "disclosure_scope": "canada_general_insurance", "basis": STATUS[period[-2:]].split("_")[1],
                    "source_document_hash": digest, "reviewed_by": "automatic-checks-v1", "source_locator": "Aviva Canada media statement",
                    "period_excerpt": excerpt, "scope_excerpt": "Aviva Canada Combined Operating Ratio (COR*), undiscounted basis",
                    "checks": ["ratio_period_label", "undiscounted_basis", "ratio_bounds"], "fetched_at": now.isoformat(),
                    "metric_id": "combined_ratio", "value": value, "unit": "PERCENT"}
        rows.append({"observation_id": f"AV-{period}-combined_ratio", "company_id": "AV", "metric_id": "combined_ratio",
                     "period_id": period, "value": value, "unit": "PERCENT", "period_end": period_end(period).isoformat(),
                     "calendar_basis": "calendar", "disclosure_scope": "canada_general_insurance", "source_url": url,
                     "source_document_hash": digest, "validation_status": STATUS[period[-2:]],
                     "evidence_json": json.dumps(evidence, sort_keys=True)})
        decisions.append({"period_id": period, "url": url, "decision": "accepted", "value": value})
    return rows, decisions
