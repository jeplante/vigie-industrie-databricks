"""P&C acquisition with optional Delta staging, automatic discovery and automatic publication.

`--discover` builds the manifest from the published quarters and the newsroom results releases instead of
reading `--manifest`; `--auto-publish` publishes the candidates that pass the automatic review
(`pnc_auto_review`) and fails the run, after publishing the others, when a candidate is rejected.
"""

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
    parser.add_argument("--manifest")
    parser.add_argument("--discover", action="store_true", help="build the manifest from Gold and the newsroom releases")
    parser.add_argument("--auto-publish", action="store_true", help="publish candidates that pass the automatic review")
    parser.add_argument("--dry-run", choices=("true", "false"), default="false",
                        help="true: discover, acquire and review without writing anything (staging or Gold)")
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
    dry_run = args.dry_run == "true"
    review_only = dry_run and args.auto_publish
    if dry_run:  # nothing is written; the automatic review still runs and reports its decisions
        args.persist = args.auto_publish = False
    if bool(args.manifest) == args.discover:
        parser.error("give exactly one of --manifest or --discover")
    if args.auto_publish and not args.persist:
        parser.error("--auto-publish requires --persist")
    contract = load_insurer_contract(Path(args.config_directory))
    prior = {}
    spark = None
    if args.persist or args.discover or review_only:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
    if args.discover:
        from datetime import UTC, datetime
        from vigie_databricks.pnc_discovery import discover_manifest

        gold = [row.asDict() for row in spark.table(f"{args.namespace}.pnc_gold_observations").collect()]
        news = [row.asDict() for row in spark.sql(
            f"SELECT company_id, title, source_url FROM {args.namespace}.pnc_official_news "
            "WHERE COALESCE(published_at, fetched_at) >= current_timestamp() - INTERVAL 120 DAYS").collect()]
        pages = {company: source.url for company, source in contract.financial_sources.items()}
        hosts = {company: source.allowed_hosts for company, source in contract.financial_sources.items()}
        manifest, new = discover_manifest(gold, news, pages, now=datetime.now(UTC), allowed_hosts=hosts)
        if not new:
            print(json.dumps({"status": "nothing_new", "manifest": manifest}, sort_keys=True))
            return
    else:
        manifest = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))["sources"]
    if args.persist:
        from vigie_databricks.pnc_storage import load_pnc_document_index
        prior = load_pnc_document_index(spark, args.namespace)
    result = acquire_pnc_documents(contract, manifest, prior, persist_raw=args.persist)
    unavailable = sorted(entry["company_id"] for entry in manifest if entry.get("unavailable_reason"))
    expected_without_candidate = sorted(
        entry["company_id"] for entry in manifest if entry.get("expected_no_candidate_reason")
    )
    candidate_companies = {row["company_id"] for row in result.candidates}
    document_companies = {document.company_id for document in result.documents}
    if set(expected_without_candidate) & candidate_companies:
        raise ValueError("Expected no-candidate source produced a candidate; review the manifest")
    audit = None
    if args.persist:
        from vigie_databricks.pnc_storage import persist_pnc_acquisition
        audit = persist_pnc_acquisition(spark, args.namespace,
                                        args.run_id, result, contract.companies,
                                        unavailable_sources=unavailable + [
                                            company for company in expected_without_candidate
                                            if company in document_companies
                                        ])
    missing = sorted(set(contract.companies) - candidate_companies)
    known_gap = set(unavailable) | (set(expected_without_candidate) & document_companies)
    unexpected_missing = sorted(set(missing) - known_gap)
    publication = None
    if (args.auto_publish or review_only) and not result.errors:
        publication = _auto_publish(spark, args.namespace, result, contract, write=not review_only)
    print(json.dumps({
        "status": "acquisition_failed" if result.errors else "extraction_incomplete" if unexpected_missing else "acquired_needs_review",
        "dry_run": not args.persist, "published": bool(publication and publication["published"]), "ai_model_calls": 0,
        "audit": audit, "auto_publication": publication,
        "sources_without_candidates": missing,
        "explicitly_unavailable_sources": unavailable,
        "expected_no_candidate_sources": expected_without_candidate,
        **asdict(result),
    }, default=str, sort_keys=True))
    if result.errors or unexpected_missing:
        raise SystemExit(1)
    if publication and publication["rejected"]:  # the others are published; the rejection is surfaced so the Job alerts
        raise SystemExit(f"P&C automatic review rejected {len(publication['rejected'])} candidate(s)")


def _auto_publish(spark, namespace, result, contract, write=True):
    """Review this run's candidates automatically and publish the accepted ones through the publication gate.

    With ``write=False`` the review and the gate run, but nothing is stored."""
    from vigie_databricks.pnc_auto_review import review_automatically
    from vigie_databricks.pnc_publication import gold_rows, publish_pnc_candidates
    from vigie_databricks.pnc_storage import publish_pnc_gold

    published = [row.asDict() for row in spark.table(f"{namespace}.pnc_gold_observations").collect()]
    accepted, decisions = review_automatically(result.candidates, published)
    rejected = [decision for decision in decisions if decision["decision"] == "rejected"]
    count = 0
    if accepted:
        gate = publish_pnc_candidates(accepted, [asdict(document) for document in result.documents], [], contract)
        if gate.quality_status != "current":
            rejected.append({"decision": "rejected", "reason": f"publication_gate: {', '.join(gate.rejection_reasons)}"})
        elif write:
            count = publish_pnc_gold(spark, namespace, gold_rows(gate.observations))
    return {"published": count, "decisions": decisions, "rejected": rejected}


if __name__ == "__main__":
    main()
