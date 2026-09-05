"""Databricks wheel entry point for guarded live Finance publication."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations
from vigie_databricks.finance_live import acquire_live_finance
from vigie_databricks.finance_ai import call_finance_model, invoke_finance_ai
from vigie_databricks.finance_publication import publish_finance_candidates
from vigie_databricks.finance_storage import load_financial_document_index, upsert_finance_run_audit, upsert_financial_documents
from vigie_databricks.gold import load_gold_observations
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.silver import load_silver_observations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-directory", required=True)
    parser.add_argument("--documents-object", required=True)
    parser.add_argument("--bronze-object", required=True)
    parser.add_argument("--silver-object", required=True)
    parser.add_argument("--gold-object", required=True)
    parser.add_argument("--audit-object", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", choices=("true", "false"), default="true")
    parser.add_argument("--ai-fallback", choices=("true", "false"), default="true")
    parser.add_argument("--ai-model", default="")
    return parser.parse_args()


def main() -> None:
    args = _arguments(); dry_run = args.dry_run == "true"
    spark = SparkSession.builder.getOrCreate()
    contract = load_insurer_contract(Path(args.config_directory))
    prior = load_financial_document_index(spark, args.documents_object)
    remaining_calls = contract.finance_policy.ai_max_calls_per_run

    def ai_fallback(company_id, period_id, source_url, content_hash, source_text):
        nonlocal remaining_calls
        if args.ai_fallback != "true" or remaining_calls <= 0:
            return []
        metric_id = "core_eps"
        skeleton = {
            "observation_id": f"{company_id}-{period_id}-{metric_id}", "company_id": company_id,
            "metric_id": metric_id, "period_id": period_id, "value": 0.0,
            "unit": contract.metrics[metric_id].unit, "source_url": source_url,
            "source_document_hash": content_hash, "quality_status": "candidate",
        }
        remaining_calls -= 1
        parsed = invoke_finance_ai(
            skeleton, source_text, contract, enabled=True, remaining_calls=1,
            invoke=lambda payload: call_finance_model(payload, args.ai_model or contract.finance_policy.ai_model),
        )
        return [parsed["candidate"]] if parsed else []

    result = acquire_live_finance(contract, prior, persist_raw=not dry_run, ai_fallback=ai_fallback)
    all_sources = result.sources_succeeded == len(contract.financial_sources)
    audit = {
        "run_id": args.run_id, "observed_at": datetime.now(UTC),
        "source_mode": "live_dry_run" if dry_run else "live",
        "sources_succeeded": result.sources_succeeded,
        "sources_failed": len(result.source_errors),
        "documents_discovered": result.documents_discovered,
        "documents_fetched": result.documents_fetched,
        "documents_unchanged": result.documents_unchanged,
        "candidate_observations": len(result.candidates),
        "quality_status": "validated" if all_sources else "stale",
    }
    if dry_run:
        print(json.dumps({"status": "validated" if all_sources else "failed", "dry_run": True, "errors": result.source_errors, "audit": audit}, default=str, sort_keys=True))
        if not all_sources:
            raise ValueError("Live Finance gate failed; schedule must remain disabled")
        return
    upsert_financial_documents(spark, args.documents_object, result.documents)
    if not all_sources:
        upsert_finance_run_audit(spark, args.audit_object, audit)
        raise ValueError("Live Finance gate failed; last-known-good publication preserved")
    prior_published = [row.asDict(recursive=True) for row in spark.table(args.bronze_object).collect()] if spark.catalog.tableExists(args.bronze_object) else []
    publication = publish_finance_candidates(list(result.candidates), prior_published, contract)
    if publication.quality_status != "current":
        audit["quality_status"] = "stale"; upsert_finance_run_audit(spark, args.audit_object, audit)
        raise ValueError("Live Finance candidates rejected; last-known-good publication preserved")
    bronze = load_bronze_observations(spark, publication.observations, args.bronze_object)
    silver = load_silver_observations(spark, args.bronze_object, args.silver_object)
    if silver.reconciliation_delta != 0:
        raise ValueError("Finance Silver reconciliation failed")
    gold = load_gold_observations(spark, args.silver_object, args.gold_object)
    if gold.reconciliation_delta != 0:
        raise ValueError("Finance Gold reconciliation failed")
    audit["quality_status"] = "current"; upsert_finance_run_audit(spark, args.audit_object, audit)
    print(json.dumps({"status": "success", "audit": audit, "bronze": asdict(bronze), "silver": asdict(silver), "gold": asdict(gold)}, default=str, sort_keys=True))
