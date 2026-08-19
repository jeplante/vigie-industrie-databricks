from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from vigie_databricks.gold import load_gold_observations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--silver-object", required=True)
    parser.add_argument("--gold-object", required=True)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    result = load_gold_observations(
        spark=SparkSession.builder.getOrCreate(),
        silver_object=arguments.silver_object,
        gold_object=arguments.gold_object,
    )
    print(json.dumps({"layer": "gold", "status": "success", "metrics": asdict(result)}, default=str, sort_keys=True))