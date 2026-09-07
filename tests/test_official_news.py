import pytest
from vigie_databricks.official_news import Page, acquire_official_news, make_row


def test_filters_ir_topics_and_external_links():
    listing = '''<a href="/news-and-events/news/2026/earnings.html">Quarterly earnings results</a>
    <a href="https://other.test/news/2026/fake.html">Earnings</a>
    <a href="/news-and-events/news/2026/sport.html">Sports sponsorship</a>'''
    rows = acquire_official_news('GWO', reader=lambda url, host: listing if url.endswith('news.html') else '<meta name="description" content="Official excerpt">')
    assert len(rows) == 1
    assert rows[0]['summary'] == 'Official excerpt'
    assert rows[0]['relevant_company_ids'] == ['GWO']
    assert rows[0]['published_at'] is None


def test_custom_cards_and_nested_titles():
    page = Page(); page.feed('<aem-card href="/news/2026/a"><h3>Financial results</h3></aem-card>')
    assert page.links == [('/news/2026/a', 'Financial results')]


def test_empty_source_fails_closed():
    with pytest.raises(ValueError, match='no official investor news'):
        acquire_official_news('SLF', reader=lambda *args: '')


def test_hash_is_stable_across_fetches():
    a = make_row('MFC', 'https://www.manulife.com/report.pdf', 'Results', 'Excerpt')
    b = make_row('MFC', 'https://www.manulife.com/report.pdf', 'Results', 'Excerpt')
    assert a['content_hash'] == b['content_hash']
    assert a['article_id'] == b['article_id']
