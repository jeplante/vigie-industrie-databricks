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

    @classmethod
    def from_environment(cls) -> "GoldConfig":
        values = {
            "catalog": os.environ.get("GOLD_CATALOG", ""),
            "schema": os.environ.get("GOLD_SCHEMA", ""),
            "gold_table": os.environ.get("GOLD_TABLE", ""),
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
        WHERE company_id IS NOT NULL
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