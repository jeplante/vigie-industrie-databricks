"""Extract auditable historical candidates without advancing published Gold."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from databricks.connect import DatabricksSession
from databricks.sdk import WorkspaceClient
from vigie_databricks.insurer_contract import load_insurer_contract, parse_finance_observation_candidate
from vigie_databricks.finance_extraction import extract_document_text, extract_finance_metrics
from vigie_databricks.finance_history import REVIEW_STATUS, select_preferred_documents


def main():
    spark = DatabricksSession.builder.profile('jeplante').serverless().getOrCreate()
    client = WorkspaceClient(profile='jeplante')
    contract = load_insurer_contract(Path('config'))
    docs = spark.sql("SELECT * FROM workspace.vigie.financial_documents WHERE reporting_period >= '2022-Q1' AND raw_content_path IS NOT NULL").collect()
    selected = select_preferred_documents(row.asDict(recursive=True) for row in docs)
    rows, errors, coverage = [], {}, Counter()
    for (company, period), doc in sorted(selected.items()):
        try:
            response = client.files.download(doc['raw_content_path'])
            with response.contents as stream:
                content = stream.read(15_000_001)
            if len(content) > 15_000_000 or sha256(content).hexdigest() != doc['content_hash']:
                raise ValueError('raw size or provenance hash mismatch')
            content_type = doc['content_type']
            if content.startswith(b'%PDF-'):
                content_type = 'application/pdf'
            text = extract_document_text(content, content_type)
            extracted = extract_finance_metrics(company, text, contract)
            coverage[company] += len(extracted)
            for metric in extracted:
                candidate = {'observation_id': f'{company}-{period}-{metric.metric_id}', 'company_id': company,
                    'period_id': period, 'metric_id': metric.metric_id, 'value': metric.value, 'unit': metric.unit,
                    'source_url': doc['source_url'], 'source_document_hash': doc['content_hash'], 'quality_status': 'candidate'}
                try:
                    parse_finance_observation_candidate(candidate, contract)
                    status = REVIEW_STATUS
                except ValueError as exc:
                    status = 'rejected: ' + str(exc)[:180]
                rows.append({**candidate, 'context': metric.context, 'validation_status': status})
            print(json.dumps({'company': company, 'period': period, 'candidates': len(extracted)}), flush=True)
        except Exception as exc:
            errors[f'{company}/{period}'] = type(exc).__name__ + ': ' + str(exc)[:150]
    schema = 'observation_id string,company_id string,period_id string,metric_id string,value double,unit string,source_url string,source_document_hash string,quality_status string,context string,validation_status string'
    target = 'workspace.vigie.finance_history_candidates'
    if not spark.catalog.tableExists(target):
        spark.createDataFrame([], schema).write.format('delta').saveAsTable(target)
    if errors:
        raise ValueError('historical extraction failed; candidate snapshot preserved: ' + json.dumps(errors, sort_keys=True))
    spark.createDataFrame(rows, schema).createOrReplaceTempView('finance_history_candidates_batch')
    try:
        spark.sql(f"MERGE INTO {target} t USING finance_history_candidates_batch s ON t.observation_id=s.observation_id WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT * WHEN NOT MATCHED BY SOURCE AND t.period_id >= '2022-Q1' THEN DELETE")
    finally:
        spark.catalog.dropTempView('finance_history_candidates_batch')
    print(json.dumps({'documents': len(selected), 'candidates': len(rows), 'coverage': dict(coverage), 'errors': errors,
                      'published': False, 'reason': 'Extractor does not yet distinguish quarterly versus annual totals or accounting restatements.'}), flush=True)


if __name__ == '__main__':
    main()
