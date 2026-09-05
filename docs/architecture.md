# Architecture notes

This repository contains the Databricks implementation of the Vigie insurer monitoring project, including the validated News pipeline and the locally integrated insurer Finance contract through Slice 14.

## Scope boundaries

- Slice 0 creates the repository skeleton, package metadata, minimal bundle config, and validation tests only.
- Finance publication validates a complete candidate batch before advancing Bronze, Silver, and Gold.
- Invalid Finance batches preserve the last-known-good tables and are recorded in `finance_run_audit`.
- Live source access is disabled by default and raw content is retained in a Unity Catalog volume according to the versioned policy.
- Slice 1 excludes Silver and Gold layers, scheduling, streaming, and MLflow.

## Intended future architecture

The target implementation should follow a disciplined progression:

1. Python package code for acquisition, parsing, validation, and business logic.
2. Databricks Asset Bundle descriptor for deployment metadata and orchestration.
3. Notebook modules kept thin for exploration and diagnostics.
4. Bronze is implemented in Slice 1; Silver and Gold remain deferred.

## Decision rationale

- The project is designed to teach Databricks engineering practices while remaining compatible with Databricks Free Edition constraints.
- The current slice avoids assumptions about availability of enterprise-only features.
- The goal is to validate Bronze ingestion discipline and idempotence before introducing Silver.
