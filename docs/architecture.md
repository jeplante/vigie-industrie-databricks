# Architecture notes

This repository intentionally contains only the Slice 0 foundation for the Databricks migration of the Vigie project.

## Scope boundaries

- Slice 0 creates the repository skeleton, package metadata, minimal bundle config, and validation tests only.
- Slice 1 will introduce the first business-facing Databricks pipeline components.
- No business YAML, source adapters, jobs, notebooks, or Delta tables are created in this slice.

## Intended future architecture

The target implementation should follow a disciplined progression:

1. Python package code for acquisition, parsing, validation, and business logic.
2. Databricks Asset Bundle descriptor for deployment metadata and orchestration.
3. Notebook modules kept thin for exploration and diagnostics.
4. Bronze / Silver / Gold layers introduced only when the data contract is stable.

## Decision rationale

- The project is designed to teach Databricks engineering practices while remaining compatible with Databricks Free Edition constraints.
- The current slice avoids assumptions about availability of enterprise-only features.
- The goal is to establish a clean foundation before introducing data assets.
