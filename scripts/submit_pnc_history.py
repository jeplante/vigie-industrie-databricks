"""Submit one bounded, unscheduled P&C historical staging run (never Gold)."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobEnvironment, SubmitTask
from databricks.sdk.service.workspace import ImportFormat
import yaml

from vigie_databricks.finance_documents import _validate_source_url
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]
HISTORY = (ROOT / "config" / "pnc" / "history").resolve()


def checked_manifest(path: Path):
    path = path.resolve()
    if path.parent != HISTORY or not re.fullmatch(r"20\d{2}-Q[1-4]", path.stem):
        raise ValueError("Manifest must be a versioned quarter under config/pnc/history")
    contract = load_insurer_contract(ROOT / "config" / "pnc")
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]
    companies = [entry["company_id"] for entry in entries]
    if len(entries) != len(contract.companies) or set(companies) != set(contract.companies):
        raise ValueError("Historical manifest must contain exactly one source per insurer")
    for entry in entries:
        if entry["period_id"] != path.stem or entry["document_type"] != "quarterly_report":
            raise ValueError("Manifest period or document type does not match the quarter")
        _validate_source_url(contract.financial_sources[entry["company_id"]], entry["source_url"])
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--profile", default="jeplante")
    parser.add_argument("--run-token", required=True, help="Unique retry-stable token for this one-time run")
    parser.add_argument("--submit", action="store_true", help="Upload and submit; otherwise validate only")
    args = parser.parse_args()
    manifest = checked_manifest(args.manifest)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,48}", args.run_token):
        parser.error("--run-token must be 1-48 safe characters")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    wheel_name = f"vigie_databricks_foundation-{version}-py3-none-any.whl"
    wheel = ROOT / "dist" / wheel_name
    if not wheel.is_file():
        raise FileNotFoundError(f"Build the {version} wheel before submitting")
    summary = {"period_id": manifest.stem, "version": version, "submitted": False}
    if not args.submit:
        print(json.dumps(summary))
        return
    client = WorkspaceClient(profile=args.profile)
    user = client.current_user.me().user_name
    if not user or "/" in user or "\\" in user:
        raise ValueError("Could not resolve a safe workspace user path")
    remote = f"/Workspace/Users/{user}/vigie_pnc_history/{version}/{manifest.stem}"
    client.workspace.mkdirs(remote + "/config/pnc")
    files = [(wheel, remote + "/" + wheel_name),
             (manifest, remote + "/pnc_source_manifest.yaml")]
    files.extend((file, remote + "/config/pnc/" + file.name)
                 for file in (ROOT / "config" / "pnc").glob("*.yaml"))
    for local, target in files:
        with local.open("rb") as stream:
            client.workspace.upload(target, stream, format=ImportFormat.AUTO, overwrite=True)
    spec = json.loads((ROOT / "databricks_pnc_acquire_job.template.json").read_text(encoding="utf-8")
                      .replace("<workspace-path>", remote))
    spec["environments"][0]["spec"]["dependencies"] = [remote + "/" + wheel_name]
    token = hashlib.sha256(f"{version}:{manifest.stem}:{args.run_token}".encode()).hexdigest()
    wait = client.jobs.submit(
        run_name=f"vigie-pnc-history-{manifest.stem}",
        idempotency_token=token,
        environments=[JobEnvironment.from_dict(item) for item in spec["environments"]],
        tasks=[SubmitTask.from_dict(item) for item in spec["tasks"]],
    )
    summary.update(submitted=True, run_id=wait.response.run_id, remote=remote)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
