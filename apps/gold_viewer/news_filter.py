"""Pure helpers for the per-insurer news filters (type, source, category)."""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _source_label(article: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    source = str(article.get("source") or "")
    return labels.get(source, source)


def news_facets(articles: Iterable[Mapping[str, Any]], labels: Mapping[str, str]) -> tuple[list[str], list[str], list[str]]:
    """Distinct, sorted filter options: (types, sources, categories)."""
    kinds, sources, categories = set(), set(), set()
    for article in articles:
        if article.get("news_kind"):
            kinds.add(str(article["news_kind"]))
        label = _source_label(article, labels)
        if label:
            sources.add(label)
        categories.update(str(category) for category in (article.get("categories") or []) if category)
    return sorted(kinds), sorted(sources), sorted(categories)


def filter_articles(
    articles: Iterable[Mapping[str, Any]],
    labels: Mapping[str, str],
    kinds: Iterable[str] = (),
    sources: Iterable[str] = (),
    categories: Iterable[str] = (),
) -> list[Mapping[str, Any]]:
    """Keep articles matching every non-empty selection; an empty selection filters nothing.

    Within one filter the selections are alternatives (any category matches); across filters
    they combine (type and source and category).
    """
    kinds, sources, categories = set(kinds), set(sources), set(categories)
    result = []
    for article in articles:
        if kinds and article.get("news_kind") not in kinds:
            continue
        if sources and _source_label(article, labels) not in sources:
            continue
        if categories and not categories.intersection(str(c) for c in (article.get("categories") or [])):
            continue
        result.append(article)
    return result
