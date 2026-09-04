from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pyspark.sql import SparkSession
from vigie_databricks.news_ai import load_news_ai

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--silver-object",required=True); p.add_argument("--enrichment-object",required=True); p.add_argument("--model",default=None); p.add_argument("--max-model-calls",type=int,default=10); p.add_argument("--audit-object",default=None); p.add_argument("--run-id",default=None); a=p.parse_args()
    print(json.dumps(asdict(load_news_ai(SparkSession.builder.getOrCreate(), a.silver_object, a.enrichment_object, a.model, max_model_calls=a.max_model_calls, audit_object=a.audit_object, run_id=a.run_id)), default=str, sort_keys=True))
