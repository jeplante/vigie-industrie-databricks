from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Sequence

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COMPARISON_COLUMNS = (
    "company_id",
    "metric_id",
    "current_period_id",
    "current_value",
    "previous_period_id",
    "previous_value",
    "change_value",
    "change_pct",
    "direction",
)


@dataclass(frozen=True)
class GoldConfig:
    catalog: str
    schema: str
    gold_table: str
    news_table: str = "gold_news"
    news_ai_audit_table: str = "news_ai_run_audit"
    finance_documents_table: str = "financial_documents"
    finance_audit_table: str = "finance_run_audit"

    @classmethod
    def from_environment(cls) -> "GoldConfig":
        values = {
            "catalog": os.environ.get("GOLD_CATALOG", ""),
            "schema": os.environ.get("GOLD_SCHEMA", ""),
            "gold_table": os.environ.get("GOLD_TABLE", ""),
            "news_table": os.environ.get("GOLD_NEWS_TABLE", "gold_news"),
            "news_ai_audit_table": os.environ.get("NEWS_AI_AUDIT_TABLE", "news_ai_run_audit"),
            "finance_documents_table": os.environ.get("FINANCE_DOCUMENTS_TABLE", "financial_documents"),
            "finance_audit_table": os.environ.get("FINANCE_AUDIT_TABLE", "finance_run_audit"),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(f"Missing Gold configuration: {', '.join(sorted(missing))}")
        for name, value in values.items():
            if not IDENTIFIER_PATTERN.fullmatch(value):
                raise ValueError(f"Invalid trusted Gold identifier for {name}")
        return cls(**values)

    @property
    def qualified_table(self) -> str:
        return ".".join(f"`{part}`" for part in (self.catalog, self.schema, self.gold_table))


def connect_to_warehouse() -> Any:
    from databricks import sql
    from databricks.sdk.core import Config

    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse_id:
        raise RuntimeError("The App SQL Warehouse resource did not provide DATABRICKS_WAREHOUSE_ID")

    config = Config()
    return sql.connect(
        server_hostname=config.host.replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: config.authenticate,
    )


def _query(connection: Any, statement: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(statement, parameters)
        columns = [column[0] for column in cursor.description or ()]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_companies(connection: Any, config: GoldConfig) -> list[str]:
    rows = _query(
        connection,
        f"""
        SELECT DISTINCT company_id
        FROM {config.qualified_table}
        WHERE company_id IN ('MFC', 'SLF', 'GWO', 'IAG')
        ORDER BY company_id
        """,
    )
    return [row["company_id"] for row in rows]


def fetch_company_metrics(connection: Any, config: GoldConfig, company_id: str) -> list[str]:
    rows = _query(
        connection,
        f"""
        SELECT DISTINCT metric_id
        FROM {config.qualified_table}
        WHERE company_id = ?
          AND metric_id IS NOT NULL
        ORDER BY metric_id
        """,
        (company_id,),
    )
    return [row["metric_id"] for row in rows]


def fetch_comparison(
    connection: Any,
    config: GoldConfig,
    company_id: str,
    metric_id: str | None = None,
) -> list[dict[str, Any]]:
    filters = ["company_id = ?"]
    parameters: list[Any] = [company_id]
    if metric_id is not None:
        filters.append("metric_id = ?")
        parameters.append(metric_id)
    columns = ", ".join(COMPARISON_COLUMNS)
    return _query(
        connection,
        f"""
        SELECT {columns}
        FROM {config.qualified_table}
        WHERE {' AND '.join(filters)}
        ORDER BY metric_id
        """,
        parameters,
    )


def fetch_news(connection: Any, config: GoldConfig, company_id: str | None = None) -> list[dict[str, Any]]:
    filters = ["enrichment_status = 'succeeded'", "parse_url(source_url, 'HOST') IN ('www.manulife.com', 'www.sunlife.com', 'www.greatwestlifeco.com', 'ia.ca')"]
    parameters: list[Any] = []
    if company_id:
        filters.append("array_contains(relevant_company_ids, ?)")
        parameters.append(company_id)
    return _query(
        connection,
        f"""
        SELECT article_id, source, source_url, title, published_at,
               summary, categories, relevant_company_ids
        FROM {".".join(f"`{part}`" for part in (config.catalog, config.schema, config.news_table))}
        WHERE {' AND '.join(filters)}
        ORDER BY published_at DESC NULLS LAST, article_id
        LIMIT 20
        """,
        parameters,
    )


def fetch_latest_news_ai_audit(connection: Any, config: GoldConfig) -> dict[str, Any] | None:
    table = ".".join(
        f"`{part}`" for part in (config.catalog, config.schema, config.news_ai_audit_table)
    )
    rows = _query(
        connection,
        f"""
        SELECT run_id, observed_at, input_rows, model_calls, max_model_calls,
               succeeded_rows, failed_rows, invalid_output_rows, deferred_rows,
               model_name, prompt_version
        FROM {table}
        ORDER BY observed_at DESC, run_id DESC
        LIMIT 1
        """,
    )
    return rows[0] if rows else None


def fetch_official_news_audit(connection: Any, config: GoldConfig) -> dict[str, Any] | None:
    table = f'`{config.catalog}`.`{config.schema}`.`official_news_audit`'
    rows = _query(connection, f'SELECT run_id, observed_at, sources_succeeded, articles, inserted_rows, updated_rows, model_calls FROM {table} ORDER BY observed_at DESC LIMIT 1')
    return rows[0] if rows else None


def fetch_finance_provenance(
    connection: Any, config: GoldConfig, company_id: str, reporting_period: str
) -> dict[str, Any] | None:
    table = ".".join(f"`{part}`" for part in (config.catalog, config.schema, config.finance_documents_table))
    rows = _query(connection, f"""
        SELECT company_id, reporting_period, source_url, content_hash, fetched_at,
               acquisition_status
        FROM {table}
        WHERE company_id = ? AND reporting_period = ?
          AND acquisition_status IN ('fetched', 'unchanged')
        ORDER BY fetched_at DESC, document_id DESC
        LIMIT 1
        """, (company_id, reporting_period))
    return rows[0] if rows else None


def fetch_latest_finance_audit(connection: Any, config: GoldConfig) -> dict[str, Any] | None:
    table = ".".join(f"`{part}`" for part in (config.catalog, config.schema, config.finance_audit_table))
    rows = _query(connection, f"""
        SELECT run_id, observed_at, sources_succeeded, sources_failed,
               documents_fetched, documents_unchanged, candidate_observations,
               ai_model_calls, retention_deleted_files, quality_status
        FROM {table}
        ORDER BY observed_at DESC, run_id DESC
        LIMIT 1
        """)
    return rows[0] if rows else None
