"""Databricks task that starts the Gold viewer App ahead of the operations monitor."""

from __future__ import annotations

import argparse
import json

from databricks.sdk import WorkspaceClient

from vigie_databricks.app_lifecycle import ensure_app_running


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-name", default="vigie-gold-viewer")
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    result = ensure_app_running(WorkspaceClient(), args.app_name, timeout_seconds=args.timeout_seconds)
    print(json.dumps({"app": args.app_name, "action": result.action, "waited_seconds": round(result.waited_seconds, 1)}))


if __name__ == "__main__":
    main()
