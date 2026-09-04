"""Bounded structured AI enrichment with auditable skip semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
import time
from typing import Any
from uuid import uuid4

import requests
from databricks.sdk.core import Config
from pyspark.sql import SparkSession


PROMPT_VERSION = "slice7-news-enrichment-v2"
AUDIT_SCHEMA = (
    "run_id string,observed_at timestamp,input_rows long,model_calls long,"
    "max_model_calls long,succeeded_rows long,failed_rows long,"
    "invalid_output_rows long,deferred_rows long,model_name string,prompt_version string"
)
CATEGORIES = {
    "artificial_intelligence",
    "capital_management",
    "digital_transformation",
    "distribution",
    "financial_results",
    "insurance",
    "international_trade",
    "leadership",
    "macroeconomics",
    "manufacturing",
    "merger_acquisition",
    "other",
    "product",
    "regulation",
    "risk",
    "strategy",
    "wealth_management",
}


@dataclass(frozen=True)
class NewsAiLoadResult:
    enrichment_object: str
    input_rows: int
    model_calls: int
    succeeded_rows: int
    failed_rows: int
    invalid_output_rows: int
    deferred_rows: int
    max_model_calls: int
    run_id: str


def enrichment_input_hash(row: dict[str, Any]) -> str:
    material = "||".join([str(row.get("article_id", "")), str(row.get("content_hash", ""))])
    return hashlib.sha256(material.encode()).hexdigest()


def build_prompt(row: dict[str, Any]) -> str:
    return json.dumps({"instruction": "Return only valid json. Do not invent facts. Use empty relevant_company_ids when unsupported. Categories must be selected only from the provided list; use other when no listed category fits.", "schema": {"summary": "string", "categories": sorted(CATEGORIES), "relevant_company_ids": "array of known IDs only"}, "article": {"title": row.get("title", ""), "description": row.get("description", ""), "source_url": row.get("source_url", "")}}, ensure_ascii=False)


def parse_output(content: str, known_company_ids: set[str]) -> dict[str, Any]:
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != {"summary", "categories", "relevant_company_ids"}:
        raise ValueError("invalid_output_schema")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("invalid_summary")
    if not isinstance(value["categories"], list) or not value["categories"] or any(c not in CATEGORIES for c in value["categories"]):
        raise ValueError("invalid_categories")
    if not isinstance(value["relevant_company_ids"], list) or any(c not in known_company_ids for c in value["relevant_company_ids"]):
        raise ValueError("invalid_company_ids")
    return value


def call_model(row: dict[str, Any], model_name: str, known_company_ids: set[str]) -> tuple[dict[str, Any], dict[str, int] | None]:
    config = Config()
    payload = {"messages": [{"role": "system", "content": "Return only compact valid json. Do not include reasoning."}, {"role": "user", "content": build_prompt(row)}], "max_tokens": 512, "temperature": 0, "reasoning_effort": "low"}
    response = None
    for attempt in range(2):
        try:
            response = requests.post(f"{config.host.rstrip('/')}/serving-endpoints/{model_name}/invocations", headers={**config.authenticate(), "Content-Type": "application/json"}, json=payload, timeout=120)
            response.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError):
            if attempt == 1:
                raise
            time.sleep(1)
    assert response is not None
    body = response.json(); message = body["choices"][0]["message"]; content = message.get("content")
    if isinstance(content, list):
        content = next((part.get("text") for part in content if part.get("type") == "text"), None)
    if not content:
        raise ValueError("empty_model_output")
    return parse_output(content, known_company_ids), body.get("usage")


def ensure_news_ai_audit_table(spark: SparkSession, audit_object: str) -> None:
    if not spark.catalog.tableExists(audit_object):
        spark.createDataFrame([], schema=AUDIT_SCHEMA).write.format("delta").mode("overwrite").saveAsTable(audit_object)
        spark.table(audit_object).count()


def _write_run_audit(spark: SparkSession, audit_object: str, row: dict[str, Any]) -> None:
    ensure_news_ai_audit_table(spark, audit_object)
    source = spark.createDataFrame([row], schema=AUDIT_SCHEMA)
    view = "vigie_news_ai_run_audit_source"
    source.createOrReplaceTempView(view)
    try:
        spark.sql(
            f"MERGE INTO {audit_object} t USING {view} s ON t.run_id=s.run_id "
            "WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *"
        )
    finally:
        spark.catalog.dropTempView(view)
    spark.table(audit_object).count()


def load_news_ai(
    spark: SparkSession,
    silver_object: str,
    enrichment_object: str,
    model_name: str | None = None,
    known_company_ids: set[str] | None = None,
    max_model_calls: int = 10,
    audit_object: str | None = None,
    run_id: str | None = None,
) -> NewsAiLoadResult:
    if not 0 <= max_model_calls <= 100:
        raise ValueError("max_model_calls must be between 0 and 100")
    model = model_name or os.environ.get("NEWS_AI_MODEL", "databricks-gpt-oss-20b")
    known = known_company_ids or set()
    rows = sorted((row.asDict() for row in spark.table(silver_object).collect()), key=lambda row: row["article_id"])
    existing = {row.article_id: row.asDict() for row in spark.table(enrichment_object).collect()} if spark.catalog.tableExists(enrichment_object) else {}
    output = []; calls = 0
    for row in rows:
        input_hash = enrichment_input_hash(row); prior = existing.get(row["article_id"])
        if prior and prior.get("input_hash") == input_hash and prior.get("prompt_version") == PROMPT_VERSION and prior.get("model_name") == model and prior.get("enrichment_status") == "succeeded":
            output.append(prior); continue
        status = "succeeded"; parsed = {"summary": None, "categories": [], "relevant_company_ids": []}; usage = None; error_code = None
        if calls >= max_model_calls:
            status, error_code = "budget_deferred", "model_call_budget_exhausted"
            output.append({"article_id": row["article_id"], "input_hash": input_hash, "model_provider": "databricks", "model_name": model, "prompt_version": PROMPT_VERSION, "summary": None, "categories": [], "relevant_company_ids": [], "enrichment_status": status, "error_code": error_code, "enriched_at": datetime.now(UTC), "usage_metadata": "{}"})
            continue
        calls += 1
        try:
            parsed, usage = call_model(row, model, known)
        except (requests.RequestException, TimeoutError):
            status, error_code = "failed", "model_request_failed"
        except ValueError as error:
            status, error_code = "invalid_output", str(error)
        except Exception:
            status, error_code = "invalid_output", "invalid_model_output"
        output.append({"article_id": row["article_id"], "input_hash": input_hash, "model_provider": "databricks", "model_name": model, "prompt_version": PROMPT_VERSION, "summary": parsed["summary"], "categories": parsed["categories"], "relevant_company_ids": parsed["relevant_company_ids"], "enrichment_status": status, "error_code": error_code, "enriched_at": datetime.now(UTC), "usage_metadata": json.dumps(usage or {}, sort_keys=True)})
    schema = "article_id string,input_hash string,model_provider string,model_name string,prompt_version string,summary string,categories array<string>,relevant_company_ids array<string>,enrichment_status string,error_code string,enriched_at timestamp,usage_metadata string"
    source = spark.createDataFrame(output, schema=schema)
    source.write.format("delta").mode("overwrite").saveAsTable(enrichment_object)
    # Materialize the committed replacement before creating/upserting the audit
    # table. This avoids a same-session Unity Catalog visibility race before the
    # downstream Gold task reads the enrichment object.
    spark.table(enrichment_object).count()
    succeeded = sum(r["enrichment_status"] == "succeeded" for r in output)
    failed = sum(r["enrichment_status"] == "failed" for r in output)
    invalid = sum(r["enrichment_status"] == "invalid_output" for r in output)
    deferred = sum(r["enrichment_status"] == "budget_deferred" for r in output)
    effective_run_id = run_id or uuid4().hex
    if audit_object:
        _write_run_audit(spark, audit_object, {
            "run_id": effective_run_id,
            "observed_at": datetime.now(UTC),
            "input_rows": len(rows),
            "model_calls": calls,
            "max_model_calls": max_model_calls,
            "succeeded_rows": succeeded,
            "failed_rows": failed,
            "invalid_output_rows": invalid,
            "deferred_rows": deferred,
            "model_name": model,
            "prompt_version": PROMPT_VERSION,
        })
    return NewsAiLoadResult(enrichment_object, len(rows), calls, succeeded, failed, invalid, deferred, max_model_calls, effective_run_id)
