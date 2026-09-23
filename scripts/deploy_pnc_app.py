"""Deploy the reviewed P&C view to the existing Databricks App."""
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat


def main():
    client = WorkspaceClient(profile="jeplante")
    app_name = "vigie-gold-viewer"
    app = client.apps.get(app_name)
    remote = app.default_source_code_path
    if remote != "/Workspace/Users/jerome.plante@hotmail.com/vigie_gold_viewer":
        raise ValueError("Unexpected App source path")
    local = Path(__file__).resolve().parents[1] / "apps/gold_viewer"
    for name in ("app.py", "app.yaml", "pnc_data.py", "pnc_view.py"):
        with (local / name).open("rb") as stream:
            client.workspace.upload(f"{remote}/{name}", stream, format=ImportFormat.AUTO, overwrite=True)
    print(f"Uploaded reviewed P&C view to {remote}")


if __name__ == "__main__":
    main()
