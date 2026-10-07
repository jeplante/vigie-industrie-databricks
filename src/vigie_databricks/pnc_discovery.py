"""Build the P&C acquisition manifest automatically: which issuer has a new quarterly report, and where.

- Intact and Definity: their results release, as read from their newsroom by the P&C news task
  (title "... reports Q3-2026 results"; the release page is the document the extractor reads).
- TD: the report to shareholders follows a fixed address per fiscal quarter; it is probed.
- Aviva Canada publishes no quarterly Canadian segment and is always declared unavailable.

An issuer without a newer quarter is declared ``not_yet_published``; when no issuer has one, there is
nothing to acquire.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
import urllib.request

from vigie_databricks.operations_monitor import PNC_FISCAL_YEAR_END, announced_results_period, latest_completed_pnc_quarter
from vigie_databricks.pnc_auto_review import period_end

TD_REPORT = ("https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/"
             "{year}/q{quarter}/{year}-q{quarter}-report-shareholders-en.pdf")
SCOPE = {
    "IFC": "Intact consolidated global P&C operations; {quarter} column only",
    "DFY": "Definity consolidated Canadian P&C operations; {quarter} column only",
    "TD": "TD Insurance standalone line; fiscal quarter ended {end}",
}
USER_AGENT = "vigie-databricks/0.10 (official report reader; contact jerome.plante@hotmail.com)"


def next_period(period_id: str) -> str:
    year, quarter = int(period_id[:4]), int(period_id[-1])
    return f"{year}-Q{quarter + 1}" if quarter < 4 else f"{year + 1}-Q1"


def report_exists(url: str, timeout: float = 20) -> bool:
    """True when the official address answers 200 (HEAD, no body downloaded)."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200 and response.geturl().startswith("https://www.td.com/")
    except Exception:  # 404 or network error: not published (yet)
        return False


def discover_manifest(
    gold_rows: Iterable[dict[str, Any]],
    news_rows: Iterable[dict[str, Any]],
    results_pages: dict[str, str],
    *,
    now: datetime,
    probe: Callable[[str], bool] = report_exists,
    allowed_hosts: dict[str, Iterable[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (manifest entries, one per issuer; issuers with a new report to acquire).

    ``results_pages`` is each issuer's official results page (``config/pnc/sources.yaml``), used as the
    reference of an issuer that has nothing new. ``allowed_hosts`` (per issuer) drops a release link that the
    acquisition would refuse, rather than failing the whole run on it.
    """
    latest: dict[str, str] = {}
    for row in gold_rows:
        period = str(row.get("period_id") or "")
        company = str(row.get("company_id") or "")
        if re.fullmatch(r"20\d{2}-Q[1-4]", period) and period > latest.get(company, ""):
            latest[company] = period
    releases: dict[str, tuple[str, str]] = {}
    for article in news_rows:
        company = str(article.get("company_id") or "")
        period = announced_results_period(str(article.get("title") or ""))
        url = str(article.get("source_url") or "")
        if allowed_hosts is not None and (urlparse(url).scheme != "https" or urlparse(url).hostname not in set(allowed_hosts.get(company, ()))):
            continue
        if company in ("IFC", "DFY") and period and period > latest.get(company, "") \
                and period > releases.get(company, ("", ""))[0]:
            releases[company] = (period, url)

    def waiting(company: str, period: str) -> dict[str, Any]:
        return {"company_id": company, "period_id": period, "unavailable_reason": "not_yet_published",
                "reference_url": results_pages[company], "disclosure_scope": "no newer quarterly report found"}

    entries, new = [], []
    calendar_next = latest_completed_pnc_quarter(now)
    for company in ("IFC", "DFY"):
        if company in releases:
            period, url = releases[company]
            entries.append({"company_id": company, "period_id": period, "source_url": url, "document_type": "quarterly_report",
                            "disclosure_scope": SCOPE[company].format(quarter=period), "calendar_basis": "calendar"})
            new.append(company)
        else:
            entries.append(waiting(company, next_period(latest[company]) if company in latest else calendar_next))
    td_period = next_period(latest["TD"]) if "TD" in latest else latest_completed_pnc_quarter(now, PNC_FISCAL_YEAR_END["TD"])
    td_end = period_end(td_period, PNC_FISCAL_YEAR_END["TD"])
    td_url = TD_REPORT.format(year=td_period[:4], quarter=td_period[-1])
    if td_end < now.date() and probe(td_url):
        entries.append({"company_id": "TD", "period_id": td_period, "source_url": td_url, "document_type": "quarterly_report",
                        "disclosure_scope": SCOPE["TD"].format(end=td_end.isoformat()), "calendar_basis": "fiscal"})
        new.append("TD")
    else:
        entries.append(waiting("TD", td_period))
    entries.append({"company_id": "AV", "period_id": calendar_next, "unavailable_reason": "no_quarterly_segment_disclosure",
                    "reference_url": results_pages["AV"], "disclosure_scope": "Aviva Canada publishes no isolated Canada quarter"})
    return entries, new
