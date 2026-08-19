from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _default_vigie_tables(spark) -> set[str]:
    context = spark.sql("SELECT current_catalog() AS catalog, current_schema() AS schema").collect()[0]
    return {
        row.tableName
        for row in spark.sql(f"SHOW TABLES IN `{context['catalog']}`.`{context['schema']}`").collect()
        if row.tableName.startswith("vigie_")
    }


@pytest.fixture(autouse=True)
def cleanup_new_databricks_connect_tables(request):
    if not request.node.get_closest_marker("databricks_connect"):
        yield
        return

    spark = request.getfixturevalue("connect_spark")
    before = _default_vigie_tables(spark)
    try:
        yield
    finally:
        after = _default_vigie_tables(spark)
        created = after - before
        disposable = {
            name
            for name in created
            if name not in {"vigie_slice4_bronze", "vigie_slice4_silver", "vigie_slice4_gold"}
        }
        for prefix in ("vigie_gold_", "vigie_silver_", "vigie_bronze_"):
            for name in sorted(name for name in disposable if name.startswith(prefix)):
                spark.sql(f"DROP TABLE IF EXISTS `workspace`.`default`.`{name}`")