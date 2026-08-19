from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from pyspark.sql import SparkSession

from vigie_databricks.silver import load_silver_observations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--bronze-object", required=True)
    parser.add_argument("--silver-object", required=True)
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    result = load_silver_observations(
        spark=SparkSession.builder.getOrCreate(),
        bronze_object=arguments.bronze_object,
        silver_object=arguments.silver_object,
    )
    print(json.dumps({"layer": "silver", "status": "success", "metrics": asdict(result)}, default=str, sort_keys=True))