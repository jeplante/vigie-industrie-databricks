from __future__ import annotations

from pathlib import Path
import logging
import pandas as pd
import streamlit as st
from display import display_number, display_percentage, display_value
from chat_service import ask, compact_context, deterministic_answer
from comparison_table import comparison_html
from history_quality import flag_suspicious_history
from gold_data import GoldConfig, connect_to_warehouse, fetch_companies, fetch_comparison, fetch_finance_provenance, fetch_latest_finance_audit, fetch_latest_finance_provenance, fetch_metric_history, fetch_news, fetch_official_news_audit

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
@st.cache_data(ttl=60, show_spinner=False)
def company_document(config, company): return fetch_latest_finance_provenance(connection(), config, company)

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
current_period = max(
    (r["current_period_id"] for rows in all_rows.values() for r in rows if r.get("current_period_id")),
    default=None,
)
latest_documents = {company: company_document(config, company) for company in available_companies}
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
    st.markdown("<p class='section-eyebrow'>Fraîcheur des sources</p>", unsafe_allow_html=True)
    freshness_cards = st.columns(4)
    for card, company in zip(freshness_cards, ("MFC", "SLF", "GWO", "IAG")):
        document = latest_documents.get(company)
        period = document.get("reporting_period") if document else None
        is_current = bool(period and period == current_period)
        card.metric(company, display_value(period, "Source absente"), "À jour" if is_current else "À vérifier", delta_color="normal" if is_current else "off")
        card.caption(f"Collecté : {display_value(document.get('fetched_at') if document else None, '—')}")
    with st.expander("À surveiller", expanded=False):
        stale_companies = [company for company, document in latest_documents.items() if not document or document.get("reporting_period") != current_period]
        if stale_companies:
            st.warning("Sources hors de la période la plus récente : " + ", ".join(stale_companies) + ".")
        if finance_audit and finance_audit.get("quality_status") != "current":
            st.warning("La dernière validation Finance n’est pas `current`; la dernière publication fiable reste affichée.")
        if not stale_companies and (not finance_audit or finance_audit.get("quality_status") == "current"):
            st.success("Aucune alerte de fraîcheur ou de publication détectée.")
    st.markdown("<p class='section-eyebrow'>Comparatif en un coup d'œil</p>", unsafe_allow_html=True)
    st.subheader("Résultats des quatre compagnies")
    comparison_mode = st.radio("Période de comparaison", ["Dernière valeur disponible", "Dernière période commune"], horizontal=True, label_visibility="collapsed")
    company_periods = {company: {row.get("current_period_id") for row in rows if row.get("current_period_id")} for company, rows in all_rows.items()}
    common_periods = set.intersection(*company_periods.values()) if company_periods and all(company_periods.values()) else set()
    if comparison_mode == "Dernière période commune" and not common_periods:
        st.warning("Aucune période commune n’est actuellement publiée pour les quatre assureurs. Le comparatif reste en dernière valeur disponible afin de ne pas masquer les sources.")
    elif comparison_mode == "Dernière période commune":
        selected_period = max(common_periods)
        display_rows = {company: [row for row in rows if row.get("current_period_id") == selected_period] for company, rows in all_rows.items()}
        st.caption(f"Période commune : {selected_period}.")
    else:
        display_rows = all_rows
        periods = sorted({period for periods in company_periods.values() for period in periods})
        if len(periods) > 1:
            st.info("Les périodes de publication diffèrent selon l’assureur. La période est affichée sous chaque valeur.")
    st.caption("Une rangée par assureur. Chaque valeur conserve sa période de publication; les KPI absents restent vides.")
    st.markdown(comparison_html(display_rows if comparison_mode == "Dernière période commune" and common_periods else all_rows), unsafe_allow_html=True)
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
            selected_companies = st.multiselect("Assureurs affichés", available_companies, default=available_companies, key="history_companies")
            reviewed_rows = flag_suspicious_history(rows, selected_metric)
            suspect_count = sum(row["display_quality"] != "accepted" for row in reviewed_rows)
            frame = pd.DataFrame([row for row in reviewed_rows if row["company_id"] in selected_companies]).sort_values(["company_id", "period_id"])
            if suspect_count:
                st.warning(f"{suspect_count} point(s) historique(s) isolé(s) comme potentiellement annuels sont masqués du graphique en attendant validation. Les données sources ne sont pas modifiées.")
            if basis == "Cumul annuel" and additive:
                frame["year"] = frame["period_id"].str[:4]
                frame["display_value"] = frame.groupby(["company_id", "year"])["display_value"].cumsum()
                st.caption("Cumul annuel : somme des valeurs trimestrielles depuis le début de chaque année.")
            else: st.caption("Valeurs trimestrielles validées. Les ratios et actifs restent des valeurs de fin de trimestre.")
            st.caption("Les ruptures dans une ligne indiquent une donnée absente, non publiée ou en attente de validation.")
            st.line_chart(frame.pivot(index="period_id", columns="company_id", values="display_value"), use_container_width=True)
            source_company = st.selectbox("Rapport source du graphique", selected_companies or available_companies, key="history_source_company")
            source_period = frame.loc[frame["company_id"] == source_company, "period_id"].max() if not frame.empty else None
            source_document = fetch_finance_provenance(connection(), config, source_company, source_period) if source_period else None
            if source_document:
                st.link_button("Voir le rapport officiel du dernier point affiché ↗", source_document["source_url"], key="history-source")
        else: st.info("Aucune série historique validée n'est encore disponible pour cet indicateur.")

with company_tab:
    st.caption("Consultez tous les indicateurs, la provenance et les communiqués pour chaque assureur.")
    panels = st.tabs(available_companies)
    for company, panel in zip(available_companies, panels):
        with panel:
            rows = all_rows[company]
            st.subheader(company)
            if not rows:
                st.info("Aucun indicateur publié n’est disponible pour cet assureur.")
                continue
            period = next((row.get("current_period_id") for row in rows if row.get("current_period_id")), None)
            document = latest_documents.get(company)
            if document:
                st.caption(f"Période : {document['reporting_period']} · Vérifié le {document['fetched_at']}")
                st.link_button("Consulter le rapport officiel ↗", document["source_url"], key=f"report-{company}")
            headline = next((row for row in rows if row.get("metric_id") == "core_earnings"), None)
            solvency = next((row for row in rows if row.get("metric_id") in {"licat_ratio", "solvency_ratio"}), None)
            narrative = []
            if headline:
                variation = display_percentage(headline.get("change_pct")) if headline.get("change_pct") is not None else "variation non disponible"
                narrative.append(f"Résultat des activités de base : {display_number(headline.get('current_value'))} ({variation} vs période précédente).")
            if solvency:
                narrative.append(f"Solvabilité : {display_number(solvency.get('current_value'))} %.")
            if narrative:
                st.info(" ".join(narrative))
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

st.divider()
st.markdown("<p class='section-eyebrow'>Assistant fondé sur les données publiées</p>", unsafe_allow_html=True)
st.subheader("Questionner la Vigie")
st.caption("Les réponses sont limitées aux KPI publiés et aux documents officiels cités. Ce n'est pas un conseil financier.")
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
question = st.chat_input("Ex. Compare les bénéfices de base des quatre assureurs.")
if question:
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    context = compact_context(
        [row for rows in all_rows.values() for row in rows],
        [article for company in available_companies for article in company_news(config, company)],
        [document for document in latest_documents.values() if document],
    )
    with st.chat_message("assistant"):
        with st.spinner("Analyse des données publiées..."):
            try:
                answer = deterministic_answer(question, context) or ask(question, context, st.session_state.chat_messages[:-1])
                st.write(answer["answer"])
                used_kpis = sorted({row.get("metric_id") for row in context["comparisons"] if row.get("metric_id")})
                st.caption("KPI disponibles pour la réponse : " + ", ".join(used_kpis))
                for citation in answer.get("citations", []):
                    st.link_button(citation.get("label", "Source officielle ↗"), citation["url"], key=f"chat-{citation['url']}")
                if answer.get("caveat"):
                    st.caption(answer["caveat"])
                st.session_state.chat_messages.append({"role": "assistant", "content": answer["answer"]})
            except Exception:
                logging.getLogger(__name__).exception("Chat query failed")
                st.error("Le chat est temporairement indisponible. Les données financières restent consultables.")
