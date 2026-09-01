from __future__ import annotations

from vigie_databricks.news_ai import PROMPT_VERSION, CATEGORIES, parse_output


def test_fake_enrichment_contract_has_no_importance_or_score():
    result = parse_output(
        '{"summary":"A concise factual summary.","categories":["financial_results"],"relevant_company_ids":["C1"]}',
        {"C1"},
    )
    assert set(result) == {"summary", "categories", "relevant_company_ids"}
    assert result["categories"][0] in CATEGORIES
    assert "importance" not in result
    assert "score" not in result
    assert PROMPT_VERSION == "slice6-news-enrichment-v1"