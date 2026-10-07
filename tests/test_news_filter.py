import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"))

from news_filter import filter_articles, news_facets

LABELS = {"artemis": "Artemis", "insurance_journal": "Insurance Journal"}
ARTICLES = [
    {"article_id": "1", "source": "sunlife.com", "news_kind": "Source officielle", "categories": ["Résultats"]},
    {"article_id": "2", "source": "artemis", "news_kind": "Média sectoriel", "categories": ["Capital", "Résultats"]},
    {"article_id": "3", "source": "insurance_journal", "news_kind": "Média sectoriel", "categories": None},
]


def ids(articles):
    return [article["article_id"] for article in articles]


def test_facets_are_sorted_distinct_and_tolerate_missing_categories():
    kinds, sources, categories = news_facets(ARTICLES, LABELS)
    assert kinds == ["Média sectoriel", "Source officielle"]
    assert sources == ["Artemis", "Insurance Journal", "sunlife.com"]
    assert categories == ["Capital", "Résultats"]


def test_empty_selection_filters_nothing():
    assert ids(filter_articles(ARTICLES, LABELS)) == ["1", "2", "3"]


def test_filters_combine_across_and_alternate_within():
    assert ids(filter_articles(ARTICLES, LABELS, kinds=["Média sectoriel"])) == ["2", "3"]
    assert ids(filter_articles(ARTICLES, LABELS, sources=["Artemis", "sunlife.com"])) == ["1", "2"]
    assert ids(filter_articles(ARTICLES, LABELS, categories=["Résultats"])) == ["1", "2"]
    assert ids(filter_articles(ARTICLES, LABELS, kinds=["Média sectoriel"], categories=["Capital"])) == ["2"]
    assert ids(filter_articles(ARTICLES, LABELS, kinds=["Source officielle"], sources=["Artemis"])) == []
