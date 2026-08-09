# Vigie Databricks Slice 1

This repository now includes Slice 1 for a Databricks-based implementation of the Vigie industry monitoring project.

Current scope:
- foundation assets from Slice 0,
- a Bronze Delta loading module for observations,
- local tests proving row counts, duplicate handling, and rerun idempotence,
- a Databricks-marked acceptance test for the same Bronze behavior on runtime.

Supported runtime for this slice:
- Python 3.12

Canonical Databricks Connect integration command:
- `py -3.12 -m pytest -m databricks_connect -q -rs`

Out of scope in this slice:
- Silver and Gold transformations,
- scheduling, UI, streaming, and MLflow features.
