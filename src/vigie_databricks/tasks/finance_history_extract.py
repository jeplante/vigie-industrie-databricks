"""Re-extract auditable historical candidates on Databricks compute only."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

from vigie_databricks.finance_extraction import extract_document_text, extract_finance_metrics
from vigie_databricks.finance_history import REVIEW_STATUS, select_preferred_documents
from vigie_databricks.insurer_contract import load_insurer_contract, parse_finance_observation_candidate

SCHEMA = "observation_id string,company_id string,period_id string,metric_id string,value double,unit string,source_url string,source_document_hash string,quality_status string,context string,validation_status string"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-directory", required=True)
    parser.add_argument("--start-period", default="2022-Q1")
    parser.add_argument("--target", default="workspace.vigie.finance_history_candidates")
    args = parser.parse_args()
    spark, client = SparkSession.builder.getOrCreate(), WorkspaceClient()
    contract = load_insurer_contract(Path(args.config_directory))
    documents = [row.asDict(recursive=True) for row in spark.sql(
        f"SELECT * FROM workspace.vigie.financial_documents WHERE reporting_period >= '{args.start_period}' "
        "AND raw_content_path IS NOT NULL AND acquisition_status IN ('fetched', 'unchanged')"
    ).collect()]
    selected = select_preferred_documents(documents)
    rows, coverage, errors = [], Counter(), {}
    for (company, period), doc in sorted(selected.items()):
        try:
            response = client.files.download(doc["raw_content_path"])
            with response.contents as stream:
                content = stream.read(15_000_001)
            if len(content) > 15_000_000 or sha256(content).hexdigest() != doc["content_hash"]:
                raise ValueError("raw size or provenance hash mismatch")
            text = extract_document_text(content, "application/pdf" if content.startswith(b"%PDF-") else doc["content_type"])
            extracted = extract_finance_metrics(company, text, contract)
            coverage[company] += len(extracted)
            for metric in extracted:
                candidate = {"observation_id": f"{company}-{period}-{metric.metric_id}", "company_id": company, "period_id": period, "metric_id": metric.metric_id, "value": metric.value, "unit": metric.unit, "source_url": doc["source_url"], "source_document_hash": doc["content_hash"], "quality_status": "candidate"}
                try:
                    parse_finance_observation_candidate(candidate, contract); status = REVIEW_STATUS
                except ValueError as exc:
                    status = "rejected: " + str(exc)[:180]
                rows.append({**candidate, "context": metric.context, "validation_status": status})
        except Exception as exc:
            errors[f"{company}/{period}"] = type(exc).__name__ + ": " + str(exc)[:150]
    if errors:
        raise ValueError("historical extraction failed; candidate snapshot preserved: " + json.dumps(errors, sort_keys=True))
    source = spark.createDataFrame(rows, SCHEMA)
    source.createOrReplaceTempView("finance_history_extract_batch")
    try:
        if spark.catalog.tableExists(args.target):
            spark.sql(
                f"MERGE INTO {args.target} t USING finance_history_extract_batch s ON t.observation_id=s.observation_id "
                "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT * "
                f"WHEN NOT MATCHED BY SOURCE AND t.period_id >= '{args.start_period}' THEN DELETE"
            )
        else:
            source.write.format("delta").saveAsTable(args.target)
    finally:
        spark.catalog.dropTempView("finance_history_extract_batch")
    print(json.dumps({"documents": len(selected), "candidates": len(rows), "coverage": dict(coverage), "errors": errors}, sort_keys=True))
