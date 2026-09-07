from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st
from display import display_number, display_percentage, display_value
from gold_data import GoldConfig, connect_to_warehouse, fetch_companies, fetch_comparison, fetch_finance_provenance, fetch_latest_finance_audit, fetch_metric_history, fetch_news, fetch_official_news_audit

ADDITIVE_METRICS = {"core_earnings", "net_income", "new_business_value", "ape_sales"}

st.set_page_config(page_title="Vigie de l'industrie", page_icon="📊", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

@st.cache_resource(show_spinner=False)
def connection(): return connect_to_warehouse()
@st.cache_data(ttl=60, show_spinner=False)
def companies(config): return fetch_companies(connection(), config)
@st.cache_data(ttl=60, show_spinner=False)
def company_rows(config, company): return fetch_comparison(connection(), config, company)
@st.cache_data(ttl=60, show_spinner=False)
def history(config, metric): return fetch_metric_history(connection(), config, metric)
@st.cache_data(ttl=60, show_spinner=False)
def company_news(config, company): return fetch_news(connection(), config, company)

st.markdown("""<header class="vigie-header"><p class="vigie-eyebrow">Assurance de personnes · Canada</p><h1>Vigie de l'industrie</h1><p>MFC · SLF · GWO · IAG — résultats et actualités</p></header>""", unsafe_allow_html=True)
try:
    config = GoldConfig.from_environment()
    available_companies = companies(config)
except Exception as exc:
    st.error(f"Les données sont indisponibles : {exc}")
    st.stop()
if not available_companies:
    st.info("Aucune compagnie n'est disponible dans les données publiées.")
    st.stop()

all_rows = {company: company_rows(config, company) for company in available_companies}
metrics = sorted({r["metric_id"] for rows in all_rows.values() for r in rows if r.get("metric_id")})
with st.sidebar:
    st.caption("État des sources")
    try:
        finance_audit = fetch_latest_finance_audit(connection(), config)
        news_audit = fetch_official_news_audit(connection(), config)
    except Exception:
        finance_audit = news_audit = None
    if finance_audit:
        st.metric("Finance", f"{finance_audit['sources_succeeded']} / 4")
        st.caption(f"Vérifié : {finance_audit['observed_at']}")
    if news_audit:
        st.metric("Actualités officielles", f"{news_audit['sources_succeeded']} / 4")

summary_tab, company_tab = st.tabs(["Synthèse", "Par compagnie"])
with summary_tab:
    st.markdown("<p class='section-eyebrow'>Comparatif en un coup d'œil</p>", unsafe_allow_html=True)
    st.subheader("Résultats des quatre compagnies")
    st.caption("Une rangée par assureur, à partir des dernières données publiées.")
    summary = []
    for company, rows in all_rows.items():
        period = next((r["current_period_id"] for r in rows if r.get("current_period_id")), None)
        summary.append({"Compagnie": company, "Période": display_value(period, "Non disponible"), "Indicateurs publiés": len(rows), "Variations disponibles": sum(r.get("previous_value") is not None for r in rows)})
    st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
    st.markdown("<p class='section-eyebrow'>Comparaison multi-assureurs</p>", unsafe_allow_html=True)
    st.subheader("Évolution historique")
    if metrics:
        left, right = st.columns([2, 1])
        default_metric = "core_earnings" if "core_earnings" in metrics else metrics[0]
        with left:
            selected_metric = st.selectbox(
                "Indicateur", metrics, index=metrics.index(default_metric), key="history_metric"
            )
        with right:
            additive = selected_metric in ADDITIVE_METRICS
            basis = st.selectbox("Base", ["Trimestre", "Cumul annuel"], disabled=not additive, key="history_basis")
        try: rows = history(config, selected_metric)
        except Exception: rows = []
        if rows:
            frame = pd.DataFrame(rows).sort_values(["company_id", "period_id"])
            if basis == "Cumul annuel" and additive:
                frame["year"] = frame["period_id"].str[:4]
                frame["value"] = frame.groupby(["company_id", "year"])["value"].cumsum()
                st.caption("Cumul annuel : somme des valeurs trimestrielles depuis le début de chaque année.")
            else: st.caption("Valeurs trimestrielles validées. Les ratios et actifs restent des valeurs de fin de trimestre.")
            st.line_chart(frame.pivot(index="period_id", columns="company_id", values="value"), use_container_width=True)
        else: st.info("Aucune série historique validée n'est encore disponible pour cet indicateur.")

with company_tab:
    st.caption("Consultez tous les indicateurs, la provenance et les communiqués pour chaque assureur.")
    panels = st.tabs(available_companies)
    for company, panel in zip(available_companies, panels):
        with panel:
            rows = all_rows[company]
            st.subheader(company)
            if not rows:
                st.info("Aucun indicateur publié.")
                continue
            period = next((r["current_period_id"] for r in rows if r.get("current_period_id")), None)
            try: document = fetch_finance_provenance(connection(), config, company, period) if period else None
            except Exception: document = None
            if document:
                st.caption(f"Période : {document['reporting_period']} · Vérifié le {document['fetched_at']}")
                st.link_button("Consulter le rapport officiel ↗", document["source_url"], key=f"report-{company}")
            table = [{"Indicateur": r["metric_id"], "Période": display_value(r["current_period_id"]), "Valeur": display_number(r["current_value"]), "Variation": display_percentage(r["change_pct"]), "Tendance": display_value(r["direction"])} for r in rows]
            st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
            st.markdown("#### Actualités")
            try: articles = company_news(config, company)
            except Exception: articles = []
            if not articles: st.caption("Aucune actualité officielle n'est disponible pour cette compagnie.")
            for article in articles:
                st.markdown(f"**{article['title']}**  \n{article['source']} · {display_value(article['published_at'], 'Date non fournie')}")
                if article["summary"]: st.write(article["summary"])
                st.link_button("Consulter la source ↗", article["source_url"], key=article["article_id"])
st.caption("Données issues de sources publiques. Vérifiez toujours les documents officiels avant une décision financière.")
