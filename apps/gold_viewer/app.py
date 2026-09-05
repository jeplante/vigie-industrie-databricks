from __future__ import annotations

import streamlit as st
from pathlib import Path

from gold_data import (
    GoldConfig,
    connect_to_warehouse,
    fetch_companies,
    fetch_company_metrics,
    fetch_comparison,
    fetch_news,
    fetch_latest_news_ai_audit,
    fetch_finance_provenance,
    fetch_latest_finance_audit,
)
from display import display_number, display_percentage, display_value


st.set_page_config(page_title="Vigie de l’industrie", page_icon="📊", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


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


@st.cache_data(ttl=60, show_spinner=False)
def finance_provenance(config: GoldConfig, company_id: str, period_id: str) -> dict | None:
    return fetch_finance_provenance(connection(), config, company_id, period_id)


@st.cache_data(ttl=60, show_spinner=False)
def latest_finance_audit(config: GoldConfig) -> dict | None:
    return fetch_latest_finance_audit(connection(), config)


st.markdown('''<header class="vigie-header">
<p class="vigie-eyebrow">Assurance de personnes · Canada</p>
<h1>Vigie de l’industrie</h1>
<p>MFC · SLF · GWO · IAG — résultats et actualités</p>
</header>''', unsafe_allow_html=True)

try:
    config = GoldConfig.from_environment()
    available_companies = companies(config)
except Exception as exc:
    st.error(f"Gold data is unavailable: {exc}")
    st.stop()

with st.expander("Suivi des actualités · détails techniques", expanded=False):
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

with st.expander("Fraîcheur des données financières", expanded=False):
    try:
        finance_audit = latest_finance_audit(config)
    except Exception:
        finance_audit = None
    if finance_audit:
        first, second, third, fourth = st.columns(4)
        first.metric("Sources", f"{finance_audit['sources_succeeded']} / 4")
        second.metric("Documents inchangés", finance_audit["documents_unchanged"])
        third.metric("Appels IA", finance_audit["ai_model_calls"] or 0)
        fourth.metric("Qualité", finance_audit["quality_status"])
        st.caption(f"Run {finance_audit['run_id']} | {finance_audit['observed_at']} | expired files: {finance_audit['retention_deleted_files'] or 0}")
    else:
        st.caption("No Finance audit is available yet.")

if not available_companies:
    st.info("No companies are available in the Gold table.")
    st.stop()

st.subheader("Résultats par compagnie")
selected_company = st.selectbox("Assureur", available_companies)
available_metrics = metrics(config, selected_company)

if not available_metrics:
    st.info("No metrics are available for the selected company.")
    st.stop()

selected_metric = st.selectbox("Indicateur", available_metrics)
comparison_rows = comparison(config, selected_company, selected_metric)
company_comparison_rows = comparison(config, selected_company)

if not comparison_rows:
    st.info("No comparison row is available for the selected company and metric.")
    st.stop()

row = comparison_rows[0]
st.subheader(f"{selected_company} / {selected_metric}")

try:
    provenance = finance_provenance(config, selected_company, row["current_period_id"])
except Exception:
    provenance = None
if provenance:
    st.caption(f"Vérifié le {provenance['fetched_at']} · Période : {provenance['reporting_period']} · {provenance['acquisition_status']}")
    st.link_button("Consulter le rapport officiel ↗", provenance["source_url"])
else:
    st.caption(f"Period: {row['current_period_id']} | No matching source document is available.")

first, second, third, fourth = st.columns(4)
first.metric("Période courante", display_value(row["current_period_id"]))
second.metric("Valeur courante", display_number(row["current_value"]))
third.metric("Période précédente", display_value(row["previous_period_id"], "Non disponible"))
fourth.metric("Valeur précédente", display_number(row["previous_value"]))

first, second, third = st.columns(3)
first.metric("Variation absolue", display_number(row["change_value"]))
second.metric("Variation relative", display_percentage(row["change_pct"]))
third.metric("Tendance", display_value(row["direction"]))

st.subheader("Tous les indicateurs")
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
st.subheader("Actualités")
st.caption("Les dernières actualités de l’assureur, ou de l’ensemble du secteur lorsque le rattachement à une compagnie est indisponible.")
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
    st.link_button("Consulter la source ↗", article["source_url"])

st.divider()
st.caption("Données issues de sources publiques. Vérifiez toujours les documents officiels avant une décision financière.")
