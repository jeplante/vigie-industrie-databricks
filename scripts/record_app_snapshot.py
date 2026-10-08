"""Record one App session's SQL results to a snapshot file, for offline runs (uses the SQL warehouse once).

    python scripts/record_app_snapshot.py tmp/app_snapshot.json

Run it with the App's Python environment (``apps/gold_viewer/requirements.txt``) and the ``jeplante``
profile. It walks both universes, every history indicator and the chat history, so that
``scripts/run_app_offline.py`` can replay them. All statements run in one short warehouse session.
"""
import os
from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"
ENVIRONMENT = {"DATABRICKS_CONFIG_PROFILE": "jeplante", "DATABRICKS_WAREHOUSE_ID": "9afffea8b155f79d",
               "GOLD_CATALOG": "workspace", "GOLD_SCHEMA": "vigie", "GOLD_TABLE": "gold_observations"}


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "tmp/app_snapshot.json").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    os.environ.update(ENVIRONMENT, VIGIE_RECORD_SNAPSHOT=str(target))
    sys.path.insert(0, str(APP))
    os.chdir(APP)
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP / "app.py"), default_timeout=300)
    app.run()
    for metric in app.selectbox(key="history_metric").options:  # each indicator reads its own history
        app.selectbox(key="history_metric").set_value(metric).run()
    app.radio(key="industry_universe").set_value("Assurance de dommages").run()
    # the chat history is read only when a question is asked; read it here without calling the model
    import gold_data
    from snapshot import RecordingConnection

    config = gold_data.GoldConfig.from_environment()
    connection = RecordingConnection(gold_data.connect_to_warehouse(), target)
    gold_data.fetch_recent_history_all(connection, config, ("MFC", "SLF", "GWO", "IAG"))
    print(f"recorded {len(connection.entries)} statements to {target}; exceptions during the walk: {len(app.exception)}")


if __name__ == "__main__":
    main()
