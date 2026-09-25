"""Explicitly enabled P&C acquisition with optional Delta staging."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import yaml

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_live import acquire_pnc_documents


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-directory", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--namespace", default="workspace.vigie")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    if not args.allow_network:
        parser.error("live acquisition requires --allow-network")
    from vigie_databricks.pnc_storage import pnc_tables
    pnc_tables(args.namespace)
    if args.persist and not args.run_id:
        parser.error("--persist requires --run-id")
    contract = load_insurer_contract(Path(args.config_directory))
    manifest = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))["sources"]
    prior = {}
    spark = None
    if args.persist:
        from pyspark.sql import SparkSession
        from vigie_databricks.pnc_storage import load_pnc_document_index
        spark = SparkSession.builder.getOrCreate()
        prior = load_pnc_document_index(spark, args.namespace)
    result = acquire_pnc_documents(contract, manifest, prior, persist_raw=args.persist)
    unavailable = sorted(entry["company_id"] for entry in manifest if entry.get("unavailable_reason"))
    audit = None
    if args.persist:
        from vigie_databricks.pnc_storage import persist_pnc_acquisition
        audit = persist_pnc_acquisition(spark, args.namespace,
                                        args.run_id, result, contract.companies,
                                        unavailable_sources=unavailable)
    candidate_companies = {row["company_id"] for row in result.candidates}
    missing = sorted(set(contract.companies) - candidate_companies)
    unexpected_missing = sorted(set(missing) - set(unavailable))
    print(json.dumps({
        "status": "acquisition_failed" if result.errors else "extraction_incomplete" if unexpected_missing else "acquired_needs_review",
        "dry_run": not args.persist, "published": False, "ai_model_calls": 0,
        "audit": audit,
        "sources_without_candidates": missing,
        "explicitly_unavailable_sources": unavailable,
        **asdict(result),
    }, default=str, sort_keys=True))
    if result.errors or unexpected_missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
