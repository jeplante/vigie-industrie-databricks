"""Upload the P&C staging release and submit one unscheduled diagnostic run."""
import json
import argparse
import tomllib
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import VolumeType
from databricks.sdk.service.workspace import ImportFormat
from databricks.sdk.service.jobs import JobEnvironment, Task, JobSettings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update-job-id", type=int)
    args = parser.parse_args()
    client = WorkspaceClient(profile="jeplante")
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    wheel = f"vigie_databricks_foundation-{version}-py3-none-any.whl"
    remote = f"/Workspace/Users/jerome.plante@hotmail.com/vigie_pnc/{version}"
    if args.update_job_id:
        current = client.jobs.get(args.update_job_id)
        if current.settings.name != "vigie-pnc-acquisition-review":
            raise ValueError("Unexpected job name")
        if list(client.jobs.list_runs(job_id=args.update_job_id, active_only=True)):
            raise ValueError("Job already has an active run")
    volumes = {v.name for v in client.volumes.list("workspace", "vigie")}
    if "pnc_finance_raw" not in volumes:
        client.volumes.create("workspace", "vigie", "pnc_finance_raw", VolumeType.MANAGED)
    client.workspace.mkdirs(remote + "/config/pnc")
    files = [(root / "dist" / wheel, remote + "/" + wheel),
             (root / "tests/fixtures/pnc_source_manifest.yaml", remote + "/pnc_source_manifest.yaml")]
    files.extend((file, remote + "/config/pnc/" + file.name) for file in (root / "config/pnc").glob("*.yaml"))
    for local, target in files:
        with local.open("rb") as stream:
            client.workspace.upload(target, stream, format=ImportFormat.AUTO, overwrite=True)
    spec = json.loads((root / "databricks_pnc_acquire_job.template.json").read_text().replace("<workspace-path>", remote))
    spec["environments"][0]["spec"]["dependencies"] = [remote + "/" + wheel]
    if args.update_job_id:
        client.jobs.update(args.update_job_id, new_settings=JobSettings.from_dict(spec))
        run = client.jobs.run_now(args.update_job_id)
        print(json.dumps({"job_id": args.update_job_id, "run_id": run.run_id, "version": version}))
        return
    existing = list(client.jobs.list(name=spec["name"]))
    if existing:
        raise RuntimeError("P&C job already exists; inspect before submitting another run")
    job = client.jobs.create(name=spec["name"], max_concurrent_runs=1,
                             environments=[JobEnvironment.from_dict(e) for e in spec["environments"]],
                             tasks=[Task.from_dict(t) for t in spec["tasks"]])
    run = client.jobs.run_now(job.job_id)
    print(json.dumps({"job_id": job.job_id, "run_id": run.run_id}))


if __name__ == "__main__":
    main()
