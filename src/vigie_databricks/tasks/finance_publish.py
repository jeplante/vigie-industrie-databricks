"""Validate and atomically advance the insurer Finance snapshot."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations
from vigie_databricks.finance_publication import publish_finance_candidates
from vigie_databricks.finance_storage import upsert_finance_run_audit
from vigie_databricks.gold import load_gold_observations
from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.silver import load_silver_observations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-directory", required=True)
    parser.add_argument("--candidate-fixture-path", required=True)
    parser.add_argument("--bronze-object", required=True)
    parser.add_argument("--silver-object", required=True)
    parser.add_argument("--gold-object", required=True)
    parser.add_argument("--audit-object", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def _prior_observations(spark: SparkSession, bronze_object: str) -> list[dict]:
    if not spark.catalog.tableExists(bronze_object):
        return []
    return [row.asDict(recursive=True) for row in spark.table(bronze_object).collect()]


def main() -> None:
    arguments = _arguments()
    candidates = json.loads(Path(arguments.candidate_fixture_path).read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("candidate fixture must contain a JSON array")

    spark = SparkSession.builder.getOrCreate()
    contract = load_insurer_contract(Path(arguments.config_directory))
    publication = publish_finance_candidates(
        candidates,
        _prior_observations(spark, arguments.bronze_object),
        contract,
    )
    audit = {
        "run_id": arguments.run_id,
        "observed_at": datetime.now(UTC),
        "source_mode": "candidate_fixture",
        "sources_succeeded": 0,
        "sources_failed": 0,
        "documents_discovered": 0,
        "documents_fetched": 0,
        "documents_unchanged": 0,
        "candidate_observations": len(candidates),
        "quality_status": publication.quality_status,
    }

    if publication.quality_status != "current":
        upsert_finance_run_audit(spark, arguments.audit_object, audit)
        raise ValueError(
            "Finance candidate batch rejected; last-known-good publication preserved: "
            + "; ".join(publication.rejection_reasons)
        )

    bronze = load_bronze_observations(spark, publication.observations, arguments.bronze_object)
    silver = load_silver_observations(spark, arguments.bronze_object, arguments.silver_object)
    if silver.reconciliation_delta != 0:
        raise ValueError("Finance Silver reconciliation failed; Gold publication was not advanced")
    gold = load_gold_observations(spark, arguments.silver_object, arguments.gold_object)
    if gold.reconciliation_delta != 0:
        raise ValueError("Finance Gold reconciliation failed")
    upsert_finance_run_audit(spark, arguments.audit_object, audit)
    print(
        json.dumps(
            {
                "status": "success",
                "quality_status": "current",
                "bronze": asdict(bronze),
                "silver": asdict(silver),
                "gold": asdict(gold),
            },
            default=str,
            sort_keys=True,
        )
    )
