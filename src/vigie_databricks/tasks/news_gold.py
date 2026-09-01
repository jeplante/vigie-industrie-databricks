from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pyspark.sql import SparkSession
from vigie_databricks.news_gold import load_gold_news

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--silver-object",required=True); p.add_argument("--enrichment-object",required=True); p.add_argument("--gold-object",required=True); a=p.parse_args()
    print(json.dumps(asdict(load_gold_news(SparkSession.builder.getOrCreate(), a.silver_object, a.enrichment_object, a.gold_object)), default=str, sort_keys=True))