from __future__ import annotations

import argparse
import json
from pyspark.sql import SparkSession
from vigie_databricks.editorial_news import load_editorial_news


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources-path", required=True)
    parser.add_argument("--target", default="workspace.vigie.editorial_news")
    parser.add_argument("--dry-run", choices=["true", "false"], default="true")
    parser.add_argument("--max-articles", type=int, default=15)
    args = parser.parse_args()
    result = load_editorial_news(SparkSession.builder.getOrCreate(), args.sources_path, args.target, dry_run=args.dry_run == "true", max_articles=args.max_articles)
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
