# Architecture notes

This repository contains Slice 0 foundation plus Slice 1 Bronze ingestion for the Databricks migration of the Vigie project.

## Scope boundaries

- Slice 0 creates the repository skeleton, package metadata, minimal bundle config, and validation tests only.
- Slice 1 introduces the first business-facing Databricks pipeline component: Bronze Delta loading for observations.
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
