"""Publish the official news of every source that answered; a failing source is named and fails the run.

Same rule as the P&C newsrooms: MERGE never deletes, so a failing source keeps its last-known articles while the
others stay current; the audit records each source and the raised error makes the Job alert.
"""
import argparse
from datetime import UTC, datetime
import json
from uuid import uuid4
from pyspark.sql import SparkSession
from vigie_databricks.official_news import acquire_official_news, acquire_manulife_news, per_source_status

COMPANIES = ('MFC', 'SLF', 'GWO', 'IAG')
TARGET_TABLE = 'workspace.vigie.official_news'
AUDIT_TABLE = 'workspace.vigie.official_news_audit'
SCHEMA = 'article_id string,source string,source_url string,title string,summary string,published_at timestamp,company_id string,relevant_company_ids array<string>,categories array<string>,enrichment_status string,fetched_at timestamp,content_hash string'


def append_audit(spark, audit, audit_table=AUDIT_TABLE):
    # mergeSchema adds the per_source_json column to the existing audit table on first use.
    spark.createDataFrame([audit]).write.format('delta').mode('append').option('mergeSchema', 'true').saveAsTable(audit_table)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config-directory', required=True)
    p.add_argument('--dry-run', choices=['true', 'false'], default='true')
    p.add_argument('--run-id', default=None)
    # Overridable only so a failure drill can run against scratch tables; production keeps the defaults.
    p.add_argument('--target', default=TARGET_TABLE)
    p.add_argument('--audit-table', default=AUDIT_TABLE)
    args = p.parse_args()
    rows, errors = [], {}
    for company in COMPANIES:
        try:
            rows.extend(acquire_manulife_news(args.config_directory) if company == 'MFC' else acquire_official_news(company))
        except Exception as exc:
            errors[company] = type(exc).__name__ + ': ' + str(exc)[:200]
    per_source = per_source_status(COMPANIES, rows, errors)
    print(json.dumps({'sources_succeeded': 4-len(errors), 'articles': len(rows), 'errors': errors, 'model_calls': 0, 'per_source': per_source}), flush=True)
    failure = f"Official News sources failed: {', '.join(sorted(errors))}; their last-known articles are kept" if errors else None
    if args.dry_run == 'true':
        if failure:
            raise ValueError(failure)
        return
    spark = SparkSession.builder.getOrCreate()
    target = args.target
    if not spark.catalog.tableExists(target):
        spark.createDataFrame([], SCHEMA).write.format('delta').saveAsTable(target)
    inserted = updated = 0
    if rows:
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
    audit = {'run_id': args.run_id or uuid4().hex, 'observed_at': datetime.now(UTC), 'sources_succeeded': 4-len(errors),
             'articles': len(rows), 'inserted_rows': inserted, 'updated_rows': updated, 'model_calls': 0,
             'per_source_json': json.dumps(per_source, sort_keys=True)}
    append_audit(spark, audit, args.audit_table)
    print(json.dumps(audit, default=str), flush=True)
    if failure:  # successes are kept; the failure is surfaced so the Job alerts
        raise ValueError(failure)


if __name__ == '__main__':
    main()
