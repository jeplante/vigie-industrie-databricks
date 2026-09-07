"""Bounded historical raw acquisition; does not publish unvalidated historical KPI."""
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
import json
import html
import re
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.connect import DatabricksSession
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.finance_acquisition import acquire_discovery_page, acquire_financial_document
from vigie_databricks.finance_discovery import discover_financial_documents, DiscoveredFinancialDocument, _LinkCollector
from urllib.parse import urljoin, urlsplit
from vigie_databricks.finance_extraction import infer_reporting_period
from vigie_databricks.finance_live import discover_mfc_direct_documents
from vigie_databricks.finance_storage import upsert_financial_documents


def main():
    contract = load_insurer_contract(Path('config'))
    client = WorkspaceClient(profile='jeplante')
    spark = DatabricksSession.builder.profile('jeplante').serverless().getOrCreate()
    now = datetime.now(UTC)
    periods = [f'{year}-Q{q}' for year in range(2022, now.year + 1) for q in range(1, 5)
               if (year, q) < (now.year, (now.month - 1) // 3 + 1)]
    report = {}
    existing = {(r['company_id'], r['reporting_period']) for r in
                spark.table('workspace.vigie.financial_documents').where('raw_content_path IS NOT NULL').select('company_id', 'reporting_period').collect()}
    for company, source in contract.financial_sources.items():
        found, errors = {}, {}
        try:
            discovered = ([discover_mfc_direct_documents(datetime(int(p[:4]), int(p[-1]) * 3, 1), max_quarters=1)[0]
                           for p in periods] if company == 'MFC' else
                          discover_financial_documents(acquire_discovery_page(source), source))
            if company == 'SLF':
                archive = replace(source, url=source.url + 'quarterly-reports-archive/')
                discovered.extend(discover_financial_documents(acquire_discovery_page(archive), archive))
            for item in discovered:
                period = infer_reporting_period(f'{item.title} {item.source_url}')
                if period in periods and period not in found and item.source_url.lower().endswith('.pdf'):
                    if company == 'MFC' and period.endswith('Q4'):
                        item = replace(item, source_url=item.source_url.replace('MFC_SR_', 'MFC_QPR_'))
                    found[period] = item
        except Exception as exc:
            errors['discovery'] = type(exc).__name__
        acquired = []
        if company == 'GWO':
            for period in periods:
                if (company, period) in existing:
                    continue
                year, quarter = period[:4], int(period[-1])
                ordinal = ('1st', '2nd', '3rd', '4th')[quarter - 1]
                archive = replace(source, url=f'https://www.greatwestlifeco.com/investor-relations/financial-reports/{year}/{ordinal}-quarter-{year}-results.html')
                try:
                    links = _LinkCollector()
                    page = acquire_discovery_page(archive)
                    links.feed(page)
                    links.links.extend((m.group(2), m.group(1)) for m in re.finditer(r'"title"\s*:\s*"([^"]+)"\s*,\s*"href"\s*:\s*"([^"]+)"', html.unescape(page)))
                    matches = [(urljoin(archive.url, href), title) for href, title in links.links
                               if 'earnings release' in title.lower() or 'report to shareholders' in title.lower()]
                    for url, title in matches:
                        if urlsplit(url).hostname in source.allowed_hosts and urlsplit(url).path.endswith('.pdf'):
                            found[period] = DiscoveredFinancialDocument('quarterly_report', url, f'{period} {title}')
                            break
                except Exception as exc:
                    errors[period] = type(exc).__name__
        for period, item in sorted(found.items()):
            if (company, period) in existing:
                acquired.append(period)
                continue
            try:
                fetched = acquire_financial_document(contract, company, item.document_type, item.source_url)
                path = f'{contract.finance_policy.raw_content_volume}/{company}/{fetched.document.content_hash}.pdf'
                client.files.create_directory(f'{contract.finance_policy.raw_content_volume}/{company}')
                client.files.upload(path, BytesIO(fetched.content), overwrite=True)
                document = replace(fetched.document, reporting_period=period, raw_content_path=path)
                upsert_financial_documents(spark, 'workspace.vigie.financial_documents', [document])
                acquired.append(period)
                print(json.dumps({'company': company, 'period': period, 'status': 'raw_stored'}), flush=True)
            except Exception as exc:
                errors[period] = type(exc).__name__
                print(json.dumps({'company': company, 'period': period, 'error': type(exc).__name__}), flush=True)
        report[company] = {'acquired': acquired, 'missing': sorted(set(periods) - set(acquired)), 'errors': errors}
    print(json.dumps({'historical_raw_report': report}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
