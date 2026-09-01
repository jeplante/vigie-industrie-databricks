from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pyspark.sql import SparkSession
from vigie_databricks.news_silver import load_silver_news

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--bronze-object",required=True); p.add_argument("--silver-object",required=True); a=p.parse_args()
    print(json.dumps(asdict(load_silver_news(SparkSession.builder.getOrCreate(), a.bronze_object, a.silver_object)), default=str, sort_keys=True))