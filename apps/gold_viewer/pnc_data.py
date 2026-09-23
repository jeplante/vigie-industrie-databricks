"""Read only reviewed P&C publication, never staging candidates."""
import re


def fetch_pnc_published(connection, catalog, schema):
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in (catalog, schema)):
        raise ValueError("Invalid P&C namespace")
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT company_id, metric_id, period_id, value, unit, period_end, "
            f"calendar_basis, disclosure_scope, source_url, source_document_hash "
            f"FROM `{catalog}`.`{schema}`.`pnc_gold_observations` "
            "WHERE validation_status = 'validated_quarterly'"
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def current_pnc_rows(rows):
    periods = [row.get("period_id", "") for row in rows
               if re.fullmatch(r"20\d{2}-Q[1-4]", row.get("period_id", ""))]
    period = max(periods, default=None)
    selected = [row for row in rows if row.get("period_id") == period]
    keys = [(row["company_id"], row["metric_id"]) for row in selected]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate published P&C observation")
    return period, selected
