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

## Durable Unity Catalog contract

The durable Vigie project schema is `workspace.vigie`:

- `workspace.vigie.bronze_observations`
- `workspace.vigie.silver_observations`
- `workspace.vigie.gold_observations`

The default schema is not the durable Vigie location. Databricks Connect tests
use UUID-suffixed tables for isolation and clean those persisted tables up in
fixture teardown. These test tables are ephemeral and must not be promoted to
the durable project contract.

The Slice 5 Streamlit App consumes Gold read-only and does not trigger pipeline
processing or write to Unity Catalog.

## News + AI contract

Slice 6 keeps News separate from financial Gold:

- `workspace.vigie.bronze_news`
- `workspace.vigie.silver_news`
- `workspace.vigie.news_ai_enrichment`
- `workspace.vigie.gold_news`

The News Job is independent from the financial Job and uses a deterministic RSS
fixture for acceptance. AI enrichment uses the native Databricks Foundation Model
endpoint configured by `NEWS_AI_MODEL`; unchanged content, prompt, and model
inputs skip inference. The Streamlit App reads enriched News read-only.

## Slice 7 live News acquisition

Slice 7 adds bounded multi-source Atom/RSS acquisition while retaining the
deterministic Slice 6 fixture. The approved initial sources are Statistics
Canada's *The Daily* feeds for Manufacturing and International trade.

Live acquisition safeguards:

- HTTPS and an explicit approved-host allowlist;
- strict source JSON validation;
- 20-second request timeout;
- 1 MB response-size ceiling;
- XML content-type validation;
- maximum 25 articles per source and run;
- isolation of a failed source when another source succeeds;
- unchanged content continues to skip AI inference.

The active six-hour schedule uses the America/Toronto timezone and defaults to
live acquisition. Bounded acceptance and an identical rerun with zero model
calls passed before activation. Statistics Canada source links and attribution
must remain visible; official logos are not reused.

## Slice 8 observability and model-call budget

The News AI task has a hard, externally configurable per-run model-call budget
(`max_model_calls`, default 10). Pending articles beyond the budget are retained
as `budget_deferred` and retried deterministically on a later run. Every AI task
execution upserts one row into `workspace.vigie.news_ai_run_audit`, keyed by the
Databricks Job run ID. The read-only App shows the latest call count, budget,
success, failure, invalid-output and deferred counts.
