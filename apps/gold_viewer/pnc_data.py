"""Read only reviewed P&C publication, never staging candidates."""
import logging
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


def fetch_pnc_half_years(connection, catalog, schema):
    """Aviva Canada's half-year and full-year ratios: published apart from the quarters, never compared with them."""
    namespace = _namespace(catalog, schema)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT company_id, metric_id, period_id, value, unit, period_end, source_url, validation_status "
            f"FROM {namespace}.`pnc_gold_observations` "
            "WHERE validation_status IN ('validated_semiannual', 'validated_annual')"
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _namespace(catalog, schema):
    if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in (catalog, schema)):
        raise ValueError("Invalid P&C namespace")
    return f"`{catalog}`.`{schema}`"


def fetch_pnc_acquisition(connection, catalog, schema):
    """Latest acquisition attempt per issuer and the latest run audit (read-only status for the sidebar)."""
    namespace = _namespace(catalog, schema)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT company_id, reporting_period, acquisition_status, error_code, fetched_at FROM ("
            "SELECT company_id, reporting_period, acquisition_status, error_code, fetched_at, "
            "row_number() OVER (PARTITION BY company_id ORDER BY fetched_at DESC, document_id DESC) AS attempt_rank "
            f"FROM {namespace}.`pnc_financial_documents` WHERE company_id IN ('IFC', 'AV', 'TD', 'DFY')) "
            "WHERE attempt_rank = 1"
        )
        columns = [column[0] for column in cursor.description]
        attempts = [dict(zip(columns, row)) for row in cursor.fetchall()]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT observed_at, status, candidate_count, documents_acquired, missing_sources_json, errors_json "
            f"FROM {namespace}.`pnc_run_audit` ORDER BY observed_at DESC LIMIT 1"
        )
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return attempts, (rows[0] if rows else None)


def fetch_pnc_news(connection, catalog, schema):
    """Official P&C newsroom items (context only), the per-issuer counts and the latest run audit."""
    namespace = _namespace(catalog, schema)
    window = "COALESCE(published_at, fetched_at) >= current_timestamp() - INTERVAL 365 DAYS"

    def run(statement):
        with connection.cursor() as cursor:
            cursor.execute(statement)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    articles = run(
        "SELECT article_id, company_id, source, source_url, title, summary, published_at, categories "
        f"FROM {namespace}.`pnc_official_news` WHERE {window} "
        "ORDER BY COALESCE(published_at, fetched_at) DESC, article_id LIMIT 60"
    )
    counts = run(
        "SELECT company_id, count(*) AS n, max(COALESCE(published_at, fetched_at)) AS latest "
        f"FROM {namespace}.`pnc_official_news` WHERE {window} GROUP BY company_id"
    )
    audit = run(
        "SELECT observed_at, sources_succeeded, sources_failed, articles, per_source_json "
        f"FROM {namespace}.`pnc_news_audit` ORDER BY observed_at DESC LIMIT 1"
    )
    try:
        editorial = run(
            "SELECT article_id, source, source_url, title, summary, published_at, relevant_company_ids, categories "
            f"FROM {namespace}.`pnc_editorial_news` WHERE {window} "
            "ORDER BY COALESCE(published_at, fetched_at) DESC, article_id LIMIT 60"
        )
    except Exception:  # missing table, missing grant or outage: sector media must never hide the official news
        logging.getLogger(__name__).warning("P&C sector media unavailable", exc_info=True)
        editorial = []
    for article in editorial:  # the SQL connector returns ARRAY columns as numpy arrays
        article["relevant_company_ids"] = list(article.get("relevant_company_ids") if article.get("relevant_company_ids") is not None else [])
        article["categories"] = list(article.get("categories") if article.get("categories") is not None else [])
    return articles, counts, (audit[0] if audit else None), editorial


def current_pnc_rows(rows):
    """Reference quarter and its rows.

    The reference is the latest quarter published by a calendar-year issuer: TD's fiscal quarters end two
    months earlier, so its label runs ahead (fiscal 2026-Q3 closed on July 31) and would otherwise leave
    every other issuer N/A for two months. TD is shown under the same label; its newer quarter stays in its
    history, the chart and the chat. Without any calendar-year row, the latest quarter is used.
    """
    quarterly = [row for row in rows if re.fullmatch(r"20\d{2}-Q[1-4]", row.get("period_id", ""))]
    calendar = [row for row in quarterly if row.get("calendar_basis") != "fiscal"]
    periods = [row["period_id"] for row in (calendar or quarterly)]
    period = max(periods, default=None)
    selected = [row for row in rows if row.get("period_id") == period]
    keys = [(row["company_id"], row["metric_id"]) for row in selected]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate published P&C observation")
    return period, selected
