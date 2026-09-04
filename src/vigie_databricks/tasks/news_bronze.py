from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from pyspark.sql import SparkSession

from vigie_databricks.news_bronze import load_bronze_news


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-mode", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--sources-json")
    parser.add_argument("--fixture-path")
    parser.add_argument("--bronze-object", required=True)
    parser.add_argument("--max-articles", type=int, default=25)
    args = parser.parse_args()
    result = load_bronze_news(
        SparkSession.builder.getOrCreate(),
        args.source_mode,
        args.source_url,
        args.fixture_path,
        args.bronze_object,
        max_articles=args.max_articles,
        sources_json=args.sources_json,
    )
    print(json.dumps(asdict(result), default=str, sort_keys=True))
