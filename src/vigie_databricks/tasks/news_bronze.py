from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pyspark.sql import SparkSession
from vigie_databricks.news_bronze import load_bronze_news

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--source-mode",required=True); p.add_argument("--source-url",default=""); p.add_argument("--fixture-path"); p.add_argument("--bronze-object",required=True); a=p.parse_args()
    print(json.dumps(asdict(load_bronze_news(SparkSession.builder.getOrCreate(), a.source_mode, a.source_url, a.fixture_path, a.bronze_object)), default=str, sort_keys=True))