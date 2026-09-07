"""Bounded official investor news, with source excerpts and no model calls."""
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PAGES = {
    'SLF': 'https://www.sunlife.com/en/newsroom/news-releases/',
    'GWO': 'https://www.greatwestlifeco.com/news-and-events/news.html',
    'IAG': 'https://ia.ca/newsroom',
}
PATHS = {'SLF': '/news-releases/announcement/', 'GWO': '/news/20', 'IAG': '/newsroom/20'}
FINANCIAL = re.compile(r'earnings|results|dividend|debenture|subordinated|acquisition|financials.summit|fireside|reinsurance|share.repurchas|capital|investor', re.I)


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = {}
        self.href = None
        self.parts = []
        self.tag = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('property', attrs.get('name', ''))] = attrs.get('content', '')
        if tag in ('a', 'aem-card') and attrs.get('href'):
            self.href, self.parts, self.tag = attrs['href'], [], tag

    def handle_data(self, data):
        if self.href:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.href and tag == self.tag:
            self.links.append((self.href, ' '.join(' '.join(self.parts).split())))
            self.href = None


def read_page(url, host):
    def validate(target):
        parts = urlsplit(target)
        if parts.scheme != 'https' or parts.hostname != host or parts.username or parts.password or parts.port not in (None, 443):
            raise ValueError('unapproved official news URL')
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            validate(newurl)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    validate(url)
    with build_opener(Redirect()).open(Request(url, headers={'User-Agent': 'VigieDatabricks/1.0'}), timeout=20) as response:
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('unexpected official news content type')
        payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError('official news page exceeds limit')
        return payload.decode('utf-8', errors='replace')


def make_row(company, url, title, summary, published=None):
    return {'article_id': sha256(url.encode()).hexdigest(), 'source': f'{company} — Relations investisseurs',
            'source_url': url, 'title': title, 'summary': summary, 'published_at': published,
            'company_id': company, 'relevant_company_ids': [company], 'categories': ['Relations investisseurs'],
            'enrichment_status': 'succeeded', 'fetched_at': datetime.now(UTC),
            'content_hash': sha256((title + '\n' + summary).encode()).hexdigest()}


def acquire_manulife_news(config_directory):
    from pathlib import Path
    from vigie_databricks.insurer_contract import load_insurer_contract
    from vigie_databricks.finance_live import discover_mfc_direct_documents
    from vigie_databricks.finance_acquisition import acquire_financial_document
    from vigie_databricks.finance_extraction import infer_reporting_period
    contract = load_insurer_contract(Path(config_directory))
    for document in discover_mfc_direct_documents():
        url = document.source_url.replace('MFC_SR_', 'MFC_QPR_')
        try:
            result = acquire_financial_document(contract, 'MFC', 'quarterly_report', url)
        except Exception:
            continue
        if result.content and result.document.content_type == 'application/pdf':
            period = infer_reporting_period(document.title)
            return [make_row('MFC', url, f'Manuvie — Résultats financiers {period}',
                             'Communiqué officiel des résultats financiers. Consultez le PDF pour les chiffres et commentaires de la direction.')]
    raise ValueError('no accessible Manulife earnings release')


def acquire_official_news(company, *, limit=3, reader=read_page):
    if company not in PAGES or not 1 <= limit <= 5:
        raise ValueError('invalid official news acquisition bounds')
    url = PAGES[company]
    host = urlsplit(url).hostname
    content = reader(url, host)
    if company == 'IAG':
        year = datetime.now(UTC).year
        match = re.search(r'data-item-id="([a-f0-9]+)">' + str(year) + r'</a>', content)
        if not match:
            raise ValueError('iA current newsroom archive not found')
        content = reader(f'https://ia.ca/IA_API/APropos/getSallePresseMois?anneeItemId={match[1]}&sc_lang=en', host)
    page = Page(); page.feed(content)
    selected = {}
    for href, title in page.links:
        target = urljoin(url, href)
        if urlsplit(target).hostname == host and PATHS[company] in urlsplit(target).path and FINANCIAL.search(title):
            selected.setdefault(target, title)
    result = []
    for target, title in list(selected.items())[:limit]:
        detail = Page(); detail.feed(reader(target, host))
        summary = detail.meta.get('description') or detail.meta.get('og:description') or ''
        published = None
        timestamp = detail.meta.get('article:published_time') or detail.meta.get('date')
        if timestamp:
            try:
                published = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                pass
        result.append(make_row(company, target, title, summary, published))
    if not result:
        raise ValueError(f'no official investor news found for {company}')
    return result
