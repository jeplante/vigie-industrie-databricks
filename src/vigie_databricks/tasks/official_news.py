"""Publish only complete four-source batches; archive legacy news separately."""
import argparse
from datetime import UTC, datetime
import json
from uuid import uuid4
from pyspark.sql import SparkSession
from vigie_databricks.official_news import acquire_official_news, acquire_manulife_news

SCHEMA = 'article_id string,source string,source_url string,title string,summary string,published_at timestamp,company_id string,relevant_company_ids array<string>,categories array<string>,enrichment_status string,fetched_at timestamp,content_hash string'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config-directory', required=True)
    p.add_argument('--dry-run', choices=['true', 'false'], default='true')
    p.add_argument('--run-id', default=None)
    args = p.parse_args()
    rows, errors = [], {}
    for company in ('MFC', 'SLF', 'GWO', 'IAG'):
        try:
            rows.extend(acquire_manulife_news(args.config_directory) if company == 'MFC' else acquire_official_news(company))
        except Exception as exc:
            errors[company] = type(exc).__name__ + ': ' + str(exc)[:200]
    print(json.dumps({'sources_succeeded': 4-len(errors), 'articles': len(rows), 'errors': errors, 'model_calls': 0}), flush=True)
    if errors:
        raise ValueError('Official News source gate failed; last-known-good preserved')
    if args.dry_run == 'true':
        return
    spark = SparkSession.builder.getOrCreate()
    target = 'workspace.vigie.official_news'
    if not spark.catalog.tableExists(target):
        spark.createDataFrame([], SCHEMA).write.format('delta').saveAsTable(target)
    source = spark.createDataFrame(rows, SCHEMA)
    old = spark.table(target).select('article_id', 'content_hash')
    inserted = source.join(old, 'article_id', 'left_anti').count()
    updated = source.alias('s').join(old.alias('t'), 'article_id').where('s.content_hash <> t.content_hash').count()
    view = 'official_news_' + uuid4().hex
    source.createOrReplaceTempView(view)
    try:
        spark.sql(f'MERGE INTO {target} t USING {view} s ON t.article_id=s.article_id WHEN MATCHED AND t.content_hash <> s.content_hash THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *')
    finally:
        spark.catalog.dropTempView(view)
    audit = {'run_id': args.run_id or uuid4().hex, 'observed_at': datetime.now(UTC), 'sources_succeeded': 4,
             'articles': len(rows), 'inserted_rows': inserted, 'updated_rows': updated, 'model_calls': 0}
    spark.createDataFrame([audit]).write.format('delta').mode('append').saveAsTable('workspace.vigie.official_news_audit')
    print(json.dumps(audit, default=str), flush=True)


if __name__ == '__main__':
    main()
