"""Run the App on a recorded snapshot, without Databricks (no SQL warehouse, no chat model).

    python scripts/run_app_offline.py tmp/app_snapshot.json          # opens the App in a browser
    python scripts/run_app_offline.py tmp/app_snapshot.json --check  # headless: both universes, no exception

Record the snapshot once with ``scripts/record_app_snapshot.py``. The chat answers with its fallback.
"""
import os
from pathlib import Path
import subprocess
import sys

APP = Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"
ENVIRONMENT = {"GOLD_CATALOG": "workspace", "GOLD_SCHEMA": "vigie", "GOLD_TABLE": "gold_observations",
               "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}


def main() -> int:
    snapshot = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp/app_snapshot.json").resolve()
    if not snapshot.is_file():
        print(f"snapshot not found: {snapshot} (record it with scripts/record_app_snapshot.py)")
        return 2
    os.environ.update(ENVIRONMENT, VIGIE_OFFLINE_SNAPSHOT=str(snapshot))
    if "--check" not in sys.argv:
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(APP / "app.py")], cwd=APP)
    sys.path.insert(0, str(APP))
    os.chdir(APP)
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP / "app.py"), default_timeout=60)
    app.run()
    life = [error.value for error in app.exception]
    app.radio(key="industry_universe").set_value("Assurance de dommages").run()
    pnc = [error.value for error in app.exception]
    print(f"life exceptions: {life}\nP&C exceptions: {pnc}")
    return 1 if life or pnc else 0


if __name__ == "__main__":
    sys.exit(main())
