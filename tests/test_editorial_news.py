from datetime import UTC, datetime
from pathlib import Path

from vigie_databricks.editorial_news import editorial_row, load_sources
from vigie_databricks.news_bronze import NewsSource, parse_sources_json


def test_editorial_sources_are_allowlisted_and_typed():
    sources = load_sources(Path(__file__).parents[1] / "config" / "editorial_news_sources.json")
    assert {source.source_id for source in sources} == {"advisor_ca", "investment_executive", "insurance_journal"}
    assert {source.source_type for source in sources} == {"editorial_wealth", "editorial_insurance"}


def test_editorial_row_assigns_company_and_editorial_category():
    source = NewsSource("investment_executive", "https://www.investmentexecutive.com/feed/", source_type="editorial_wealth")
    row = editorial_row({"article_id": "a", "source_url": "https://www.investmentexecutive.com/a", "title_raw": "Manulife wealth update", "description_raw": "Sun Life also commented.", "published_at_iso": "2026-09-10T10:00:00+00:00", "fetched_at": datetime.now(UTC).isoformat(), "content_hash": "h"}, source)
    assert row["relevant_company_ids"] == ["MFC", "SLF"]
    assert row["categories"] == ["Gestion de patrimoine"]


def test_editorial_source_type_is_accepted_but_unknown_type_is_not():
    assert parse_sources_json('[{"source_id":"advisors","url":"https://www.advisor.ca/feed/","source_type":"editorial_wealth"}]')[0].source_type == "editorial_wealth"
