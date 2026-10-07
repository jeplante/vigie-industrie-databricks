from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import logging
import pandas as pd
import streamlit as st
from display import display_number, display_percentage, display_value
from chat_service import ask, compact_context, deterministic_answer, fallback_answer
from comparison_table import METRICS, comparison_html, expected_yoy_period, latest_quarter_period, rows_for_period
from history_chart import history_spec
from history_quality import flag_suspicious_history, year_to_date_values
from shared_ui import vigie_header
from news_filter import filter_articles, news_facets
from source_status import (FINANCE_ERROR_HOURS, FINANCE_WARN_HOURS, NEWS_ERROR_HOURS, NEWS_WARN_HOURS, SidebarSection, SourceRow,
                           alert_rows, audit_freshness_row, finance_sources, news_sources, render_sidebar)
from pnc_data import fetch_pnc_acquisition, fetch_pnc_news, fetch_pnc_published
from gold_data import GoldConfig, connect_to_warehouse, fetch_comparison_all, fetch_editorial_news_all, fetch_latest_finance_provenance_all, fetch_news_all, fetch_finance_document_periods, fetch_finance_provenance, fetch_latest_finance_attempts, fetch_latest_finance_audit, fetch_latest_finance_provenance, fetch_latest_operations_alerts, fetch_metric_history, fetch_official_news_audit, fetch_official_news_counts

SOURCE_COMPANIES = ("MFC", "SLF", "GWO", "IAG")
ADDITIVE_METRICS = {"core_earnings", "net_income", "new_business_value", "ape_sales"}
NEWS_SOURCE_LABELS = {
    "insurance_journal": "Insurance Journal",
    "insurance_canada": "Insurance-Canada.ca",
    "naifa_advisor_today": "Advisor Today (NAIFA)",
    "artemis": "Artemis",
}

st.set_page_config(page_title="Vigie de l'industrie", page_icon="📊", layout="wide")
st.markdown(f"<style>{Path(__file__).with_name('style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

@st.cache_resource(show_spinner=False)
def connection(): return connect_to_warehouse()
# One statement per kind of data for all four companies: the first load is dominated by the number of
# statements, not by their size, so these replace what used to be four statements each.
@st.cache_data(ttl=300, show_spinner=False)
def comparison_all(config): return fetch_comparison_all(connection(), config, SOURCE_COMPANIES)
@st.cache_data(ttl=300, show_spinner=False)
def documents_all(config): return fetch_latest_finance_provenance_all(connection(), config, SOURCE_COMPANIES)
@st.cache_data(ttl=300, show_spinner=False)
def news_all(config): return fetch_news_all(connection(), config, SOURCE_COMPANIES)
@st.cache_data(ttl=300, show_spinner=False)
def editorial_news_all(config): return fetch_editorial_news_all(connection(), config, SOURCE_COMPANIES)
def companies(config): return sorted(company for company, rows in comparison_all(config).items() if rows)
def company_rows(config, company): return comparison_all(config).get(company, [])
def company_news(config, company): return news_all(config).get(company, [])
def company_editorial_news(config, company): return editorial_news_all(config).get(company, [])
def company_document(config, company): return documents_all(config).get(company)
@st.cache_data(ttl=300, show_spinner=False)
def history(config, metric): return fetch_metric_history(connection(), config, metric)
@st.cache_data(ttl=300, show_spinner=False)
def document_periods(config): return fetch_finance_document_periods(connection(), config)
@st.cache_data(ttl=300, show_spinner=False)
def finance_provenance(config, company, period): return fetch_finance_provenance(connection(), config, company, period)
# Previously re-queried on every rerun (about 3 s per interaction on the life landing page).
# Errors are not cached by Streamlit, so the existing try/except fallbacks still apply.
@st.cache_data(ttl=300, show_spinner=False)
def finance_audit_status(config): return fetch_latest_finance_audit(connection(), config)
@st.cache_data(ttl=300, show_spinner=False)
def news_audit_status(config): return fetch_official_news_audit(connection(), config)
@st.cache_data(ttl=300, show_spinner=False)
def operations_alerts_status(config): return fetch_latest_operations_alerts(connection(), config)
@st.cache_data(ttl=300, show_spinner=False)
def finance_attempts(config): return fetch_latest_finance_attempts(connection(), config)
@st.cache_data(ttl=300, show_spinner=False)
def official_news_counts(config): return fetch_official_news_counts(connection(), config)
@st.cache_data(ttl=300, show_spinner=False)
def pnc_acquisition(catalog, schema): return fetch_pnc_acquisition(connection(), catalog, schema)
@st.cache_data(ttl=300, show_spinner=False)
def pnc_news(catalog, schema): return fetch_pnc_news(connection(), catalog, schema)
@st.cache_data(ttl=300, show_spinner=False)
def pnc_published(catalog, schema): return fetch_pnc_published(connection(), catalog, schema)

def _safe(call, default):
    try:
        return call()
    except Exception:
        return default


# Two universes of equal standing; each page reads only its own published tables.
universe = st.radio("Univers", ["Assurance vie", "Assurance de dommages"], horizontal=True, key="industry_universe")
if universe == "Assurance de dommages":
    from pnc_view import render_pnc_page
    try:
        pnc_config = GoldConfig.from_environment()
        pnc_rows = pnc_published(pnc_config.catalog, pnc_config.schema)
    except Exception:
        logging.getLogger(__name__).exception("P&C publication unavailable")
        st.warning("Les données P&C publiées sont temporairement indisponibles.")
        pnc_rows = []
    render_pnc_page(st, pnc_rows, _safe(lambda: operations_alerts_status(pnc_config), []),
                    _safe(lambda: pnc_acquisition(pnc_config.catalog, pnc_config.schema), None),
                    _safe(lambda: pnc_news(pnc_config.catalog, pnc_config.schema), None))
    st.stop()

st.markdown(vigie_header("Assurance de personnes · Canada", "Vigie de l'industrie", "MFC · SLF · GWO · IAG — résultats et actualités"), unsafe_allow_html=True)
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
latest_documents = {company: company_document(config, company) for company in available_companies}
available_document_periods = document_periods(config)
current_period = latest_quarter_period(
    all_rows,
    [str(document.get("reporting_period")) for document in available_document_periods],
)
current_rows = rows_for_period(all_rows, current_period)
now = datetime.now(UTC)
finance_audit = _safe(lambda: finance_audit_status(config), None)
news_audit = _safe(lambda: news_audit_status(config), None)
attempts = {row["company_id"]: row for row in _safe(lambda: finance_attempts(config), [])}
news_counts = {row["company_id"]: row for row in _safe(lambda: official_news_counts(config), [])}
operations_alerts = _safe(lambda: operations_alerts_status(config), [])
finance_rows = [row for row in (audit_freshness_row("Finance", finance_audit, now, FINANCE_WARN_HOURS, FINANCE_ERROR_HOURS),) if row]
if finance_audit and finance_audit.get("quality_status") != "current":
    finance_rows.append(SourceRow("Validation", "warn", "La dernière validation n'est pas `current`; la dernière publication fiable reste affichée."))
finance_rows += finance_sources(SOURCE_COMPANIES, latest_documents, attempts, current_period)
news_rows = [row for row in (audit_freshness_row("Actualités", news_audit, now, NEWS_WARN_HOURS, NEWS_ERROR_HOURS),) if row]
news_rows += news_sources(SOURCE_COMPANIES, news_counts, news_audit)
render_sidebar(
    st,
    [
        SidebarSection("Finance", f"{finance_audit['sources_succeeded']} / 4" if finance_audit else None,
                       f"Vérifié : {finance_audit['observed_at']}" if finance_audit else None, finance_rows),
        SidebarSection("Actualités officielles", f"{news_audit['sources_succeeded']} / 4" if news_audit else None, None, news_rows),
    ],
    alert_rows(operations_alerts),
)

summary_tab, company_tab = st.tabs(["Synthèse", "Par compagnie"])
with summary_tab:
    st.markdown("<p class='section-eyebrow'>Comparatif en un coup d'œil</p>", unsafe_allow_html=True)
    st.subheader("Résultats des quatre compagnies")
    st.caption(f"Trimestre affiché : {display_value(current_period, 'indisponible')}. Aucun trimestre antérieur n’est utilisé comme substitut.")
    st.caption("Les KPI absents sont indiqués N/A. Une variation est affichée uniquement si le même trimestre de l’année précédente est disponible.")
    st.markdown(comparison_html(current_rows), unsafe_allow_html=True)
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
            if suspect_count:
                st.warning(f"{suspect_count} point(s) historique(s) isolé(s) comme potentiellement annuels sont masqués du graphique en attendant validation. Les données sources ne sont pas modifiées.")
            if not selected_companies:
                st.info("Sélectionnez au moins un assureur pour afficher l’évolution historique.")
            else:
                frame = pd.DataFrame([row for row in reviewed_rows if row["company_id"] in selected_companies]).sort_values(["company_id", "period_id"])
                if basis == "Cumul annuel" and additive:
                    frame["display_value"] = year_to_date_values(frame.to_dict("records"))
                    st.caption("Cumul annuel : somme des valeurs trimestrielles depuis le début de chaque année. Après un trimestre absent ou masqué, le cumul de l’année est indiqué comme manquant.")
                else: st.caption("Valeurs trimestrielles validées. Les ratios et actifs restent des valeurs de fin de trimestre.")
                source_urls = {(document["company_id"], document["reporting_period"]): document["source_url"] for document in available_document_periods}
                frame["source_url"] = [source_urls.get((row.company_id, row.period_id)) for row in frame.itertuples()]
                documented = {(document["company_id"], document["reporting_period"]) for document in available_document_periods}
                observed = {(row.company_id, row.period_id) for row in frame.itertuples() if pd.notna(row.display_value)}
                pending = documented - observed
                st.caption(f"Ruptures : {len(pending)} période(s) avec rapport officiel mais KPI en attente de validation; les autres absences correspondent à une source non collectée ou non publiée.")
                st.vega_lite_chart(history_spec(frame.to_dict("records")), use_container_width=True)
                st.caption("Survolez un point pour voir son rapport officiel; cliquez sur un point lorsqu’un lien est disponible.")
                source_company = st.selectbox("Rapport source du graphique", selected_companies, key="history_source_company")
                source_period = frame.loc[frame["company_id"] == source_company, "period_id"].max()
                try:
                    source_document = finance_provenance(config, source_company, source_period) if pd.notna(source_period) else None
                except Exception:
                    logging.getLogger(__name__).exception("Finance provenance unavailable")
                    source_document = None
                if source_document:
                    st.link_button("Voir le rapport officiel du dernier point affiché ↗", source_document["source_url"], key="history-source")
        else: st.info("Aucune série historique validée n'est encore disponible pour cet indicateur.")

with company_tab:
    st.caption("Consultez tous les indicateurs, la provenance et les communiqués pour chaque assureur.")
    panels = st.tabs(available_companies)
    for company, panel in zip(available_companies, panels):
        with panel:
            rows = current_rows[company]
            st.subheader(company)
            if not rows:
                st.info(f"Aucun indicateur validé pour {display_value(current_period)}; les KPI sont indiqués N/A.")
            document = latest_documents.get(company)
            if document:
                st.caption(f"Période : {document['reporting_period']} · Vérifié le {document['fetched_at']}")
                st.link_button("Consulter le rapport officiel ↗", document["source_url"], key=f"report-{company}")
            headline = next((row for row in rows if row.get("metric_id") == "core_earnings"), None)
            solvency = next((row for row in rows if row.get("metric_id") in {"licat_ratio", "solvency_ratio"}), None)
            narrative = []
            if headline:
                expected_period = expected_yoy_period(headline.get("current_period_id"))
                has_yoy = headline.get("previous_period_id") == expected_period and headline.get("change_pct") is not None
                variation = display_percentage(headline.get("change_pct")) if has_yoy else "variation annuelle N/A"
                narrative.append(f"Résultat des activités de base : {display_number(headline.get('current_value'))} ({variation}).")
            if solvency:
                narrative.append(f"Solvabilité : {display_number(solvency.get('current_value'))} %.")
            if narrative:
                st.info(" ".join(narrative))
            table = []
            for selector, label, _ in METRICS:
                metric_ids = (selector,) if isinstance(selector, str) else selector
                row = next((candidate for metric_id in metric_ids for candidate in rows if candidate.get("metric_id") == metric_id), None)
                expected_period = expected_yoy_period(current_period)
                has_yoy = bool(row and row.get("previous_period_id") == expected_period and row.get("change_pct") is not None)
                table.append({
                    "Indicateur": label,
                    "Période": current_period,
                    "Valeur": display_number(row.get("current_value")) if row else "N/A",
                    "Variation annuelle": display_percentage(row.get("change_pct")) if has_yoy else "N/A",
                    "Comparaison": f"vs {expected_period}" if expected_period else "N/A",
                })
            st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
            st.markdown("#### Actualités")
            st.caption("Communiqués officiels et articles de médias sectoriels pertinents. Les articles externes apportent du contexte et ne modifient jamais les KPI publiés.")
            try: official_articles = company_news(config, company)
            except Exception: official_articles = []
            try: editorial_articles = company_editorial_news(config, company)
            except Exception: editorial_articles = []
            articles = [dict(article, news_kind="Source officielle") for article in official_articles]
            articles.extend(dict(article, news_kind="Média sectoriel") for article in editorial_articles)
            articles.sort(key=lambda article: str(article.get("published_at") or ""), reverse=True)
            if not articles:
                st.caption("Aucune actualité pertinente n’est encore disponible pour cet assureur.")
            if articles:
                kind_options, source_options, category_options = news_facets(articles, NEWS_SOURCE_LABELS)
                kind_column, source_column, category_column = st.columns(3)
                chosen_kinds = kind_column.multiselect("Type", kind_options, key=f"news-kind-{company}")
                chosen_sources = source_column.multiselect("Source", source_options, key=f"news-source-{company}")
                chosen_categories = category_column.multiselect("Catégorie", category_options, key=f"news-category-{company}")
                articles = filter_articles(articles, NEWS_SOURCE_LABELS, chosen_kinds, chosen_sources, chosen_categories)
                if not articles:
                    st.caption("Aucune actualité ne correspond aux filtres choisis.")
            for article in articles[:20]:
                source = NEWS_SOURCE_LABELS.get(article["source"], article["source"])
                metadata = [source, article["news_kind"]]
                metadata.extend(article.get("categories") or [])
                metadata.append(display_value(article["published_at"], "Date non fournie"))
                st.markdown(f"**{article['title']}**  \n{' · '.join(metadata)}")
                if article["summary"]: st.write(article["summary"])
                st.link_button("Consulter la source ↗", article["source_url"], key=f"news-{company}-{article['news_kind']}-{article['article_id']}")
st.caption("Données issues de sources publiques. Vérifiez toujours les documents officiels avant une décision financière.")

st.divider()
st.markdown("<p class='section-eyebrow'>Assistant fondé sur les données publiées</p>", unsafe_allow_html=True)
st.subheader("Questionner la Vigie")
st.caption("Les réponses sont limitées aux KPI publiés et aux documents officiels cités. Ce n'est pas un conseil financier.")
examples = (
    "Compare les bénéfices de base des quatre assureurs pour T2 2026",
    "Quel est le résultat net de iA?",
    "Compare les ratios LICAT au dernier trimestre",
)
example_columns = st.columns(3)
selected_example = None
for column, example in zip(example_columns, examples):
    if column.button(example, use_container_width=True):
        selected_example = example
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
question = selected_example or st.chat_input("Ex. Compare les bénéfices de base des quatre assureurs.")
if question:
    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    chat_news = []
    for company in available_companies:
        try:
            chat_news.extend(company_news(config, company))
        except Exception:
            continue
    context = compact_context(
        [row for rows in current_rows.values() for row in rows], chat_news,
        [document for document in latest_documents.values() if document],
    )
    with st.chat_message("assistant"):
        with st.spinner("Analyse des données publiées..."):
            try:
                answer = deterministic_answer(question, context) or ask(question, context, st.session_state.chat_messages[:-1], reasoning_effort="low")
                st.write(answer["answer"])
                used_kpis = [f"{row.get('company_id')} {row.get('metric_id')} {row.get('period_id')}" for row in answer.get("used_kpis") or []]
                if used_kpis:
                    st.caption("KPI utilisés : " + "; ".join(used_kpis))
                for index, citation in enumerate(answer.get("citations") or []):
                    st.link_button(citation.get("label", "Source officielle ↗"), citation["url"], key=f"chat-{index}-{citation['url']}")
                if answer.get("caveat"):
                    st.caption(answer["caveat"])
                st.session_state.chat_messages.append({"role": "assistant", "content": answer["answer"]})
            except Exception:
                logging.getLogger(__name__).exception("Chat query failed")
                answer = fallback_answer(context)
                st.warning(answer["answer"])
                st.caption(answer["caveat"])
                for index, citation in enumerate(answer.get("citations") or []):
                    st.link_button(citation.get("label", "Source officielle ↗"), citation["url"], key=f"chat-fallback-{index}-{citation['url']}")
                st.session_state.chat_messages.append({"role": "assistant", "content": answer["answer"]})
