from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from pyspark.sql import SparkSession

from vigie_databricks.bronze import load_bronze_observations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--bronze-object", required=True)
    parser.add_argument("--input-mode", required=True, choices=["fixture"])
    parser.add_argument("--input-fixture-path")
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    if arguments.input_mode != "fixture" or not arguments.input_fixture_path:
        raise ValueError("Bronze requires input_mode=fixture and input_fixture_path for Slice 4")

    rows = json.loads(Path(arguments.input_fixture_path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Bronze fixture must contain a JSON array of observation objects")

    result = load_bronze_observations(
        spark=SparkSession.builder.getOrCreate(),
        rows=rows,
        bronze_object=arguments.bronze_object,
    )
    print(json.dumps({"layer": "bronze", "status": "success", "metrics": asdict(result)}, default=str, sort_keys=True))