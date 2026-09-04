from __future__ import annotations

import streamlit as st

from gold_data import (
    GoldConfig,
    connect_to_warehouse,
    fetch_companies,
    fetch_company_metrics,
    fetch_comparison,
    fetch_news,
    fetch_latest_news_ai_audit,
)
from display import display_number, display_percentage, display_value


st.set_page_config(page_title="Gold comparison viewer", layout="wide")


@st.cache_resource(show_spinner=False)
def connection():
    return connect_to_warehouse()


@st.cache_data(ttl=60, show_spinner=False)
def companies(config: GoldConfig) -> list[str]:
    return fetch_companies(connection(), config)


@st.cache_data(ttl=60, show_spinner=False)
def metrics(config: GoldConfig, company_id: str) -> list[str]:
    return fetch_company_metrics(connection(), config, company_id)


@st.cache_data(ttl=60, show_spinner=False)
def comparison(config: GoldConfig, company_id: str, metric_id: str | None = None) -> list[dict]:
    return fetch_comparison(connection(), config, company_id, metric_id)


@st.cache_data(ttl=60, show_spinner=False)
def news(config: GoldConfig, company_id: str) -> list[dict]:
    return fetch_news(connection(), config, company_id)


@st.cache_data(ttl=60, show_spinner=False)
def latest_news_ai_audit(config: GoldConfig) -> dict | None:
    return fetch_latest_news_ai_audit(connection(), config)


st.title("Gold comparison viewer")
st.caption("Read-only view of the deterministic Gold comparison mart.")

try:
    config = GoldConfig.from_environment()
    available_companies = companies(config)
except Exception as exc:
    st.error(f"Gold data is unavailable: {exc}")
    st.stop()

with st.expander("News pipeline health", expanded=False):
    try:
        audit = latest_news_ai_audit(config)
    except Exception:
        audit = None
    if audit:
        first, second, third, fourth = st.columns(4)
        first.metric("Model calls", f"{audit['model_calls']} / {audit['max_model_calls']}")
        second.metric("Succeeded", audit["succeeded_rows"])
        third.metric("Deferred", audit["deferred_rows"])
        fourth.metric("Invalid / failed", audit["invalid_output_rows"] + audit["failed_rows"])
        st.caption(f"Run {audit['run_id']} | {audit['observed_at']} | {audit['model_name']} | {audit['prompt_version']}")
    else:
        st.caption("No Slice 8 AI audit is available yet.")

if not available_companies:
    st.info("No companies are available in the Gold table.")
    st.stop()

selected_company = st.selectbox("Company", available_companies)
available_metrics = metrics(config, selected_company)

if not available_metrics:
    st.info("No metrics are available for the selected company.")
    st.stop()

selected_metric = st.selectbox("Metric", available_metrics)
comparison_rows = comparison(config, selected_company, selected_metric)
company_comparison_rows = comparison(config, selected_company)

if not comparison_rows:
    st.info("No comparison row is available for the selected company and metric.")
    st.stop()

row = comparison_rows[0]
st.subheader(f"{selected_company} / {selected_metric}")

first, second, third, fourth = st.columns(4)
first.metric("Current period", display_value(row["current_period_id"]))
second.metric("Current value", display_number(row["current_value"]))
third.metric("Previous period", display_value(row["previous_period_id"], "No previous period"))
fourth.metric("Previous value", display_number(row["previous_value"]))

first, second, third = st.columns(3)
first.metric("Absolute change", display_number(row["change_value"]))
second.metric("Percentage change", display_percentage(row["change_pct"]))
third.metric("Direction", display_value(row["direction"]))

st.subheader("Available metrics")
table_rows = []
for metric_row in company_comparison_rows:
    table_rows.append(
        {
            "Metric": metric_row["metric_id"],
            "Current period": display_value(metric_row["current_period_id"]),
            "Current value": display_number(metric_row["current_value"]),
            "Previous period": display_value(metric_row["previous_period_id"], "No previous period"),
            "Previous value": display_number(metric_row["previous_value"]),
            "Absolute change": display_number(metric_row["change_value"]),
            "Percentage change": display_percentage(metric_row["change_pct"]),
            "Direction": display_value(metric_row["direction"]),
        }
    )
st.dataframe(table_rows, hide_index=True, width="stretch")

st.divider()
st.subheader("News")
st.caption("Read-only latest enriched news. Company-specific results are shown when deterministic mapping exists; otherwise the latest enriched news is shown globally.")
st.caption(
    "Statistique Canada : adapté du Quotidien (Fabrication et Commerce international). "
    "Ceci ne constitue pas un endossement de Statistique Canada."
)
news_rows = news(config, selected_company)
if not news_rows:
    news_rows = fetch_news(connection(), config)
    st.caption("No deterministic company mapping was available; showing latest enriched news globally.")
for article in news_rows:
    published = display_value(article["published_at"])
    st.markdown(f"**{article['title']}**  \n{article['source']} · {published}")
    st.write(article["summary"] or "N/A")
    categories = article.get("categories") or []
    if categories:
        st.caption("Categories: " + ", ".join(categories))
    st.link_button("Open source", article["source_url"])
