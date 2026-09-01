from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pyspark.sql import SparkSession
from vigie_databricks.news_ai import load_news_ai

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--silver-object",required=True); p.add_argument("--enrichment-object",required=True); p.add_argument("--model",default=None); a=p.parse_args()
    print(json.dumps(asdict(load_news_ai(SparkSession.builder.getOrCreate(), a.silver_object, a.enrichment_object, a.model)), default=str, sort_keys=True))