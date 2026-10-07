"""P&C landing page backed exclusively by reviewed Gold observations.

Slice 18 brings the P&C universe onto the shared visual system (branded header,
brand-colour comparison table, period chips, tooltips, single value formatter)
while keeping every P&C domain guardrail: the Périmètre / Clôture / Calendrier
columns, the divergent-close warnings, the `N/A` semantics, and a year-over-year
delta only when a same-calendar, same-quarter prior-year value exists.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from news_filter import filter_articles, news_facets
from source_status import SidebarSection, alert_rows, pnc_acquisition_rows, pnc_news_rows, pnc_sources, render_sidebar

from shared_ui import (
    delta_badge,
    empty_cell,
    format_value,
    header_cell,
    meta_cell,
    row_header_cell,
    row_open,
    table_shell,
    value_cell,
    vigie_header,
)

COMPANIES = (
    ("IFC", "Intact Financial", "Groupe consolidé"),
    ("AV", "Aviva Canada", "Segment Canada"),
    ("TD", "TD Insurance", "Activités d’assurance"),
    ("DFY", "Definity Financial", "Groupe consolidé"),
)
AVIVA_HY26_URL = "https://www.aviva.ca/en/press-releases/2026/half-year-results-2026/"
METRICS = (("insurance_revenue", "Produits d’assurance"), ("combined_ratio", "Ratio combiné"),
           ("claims_ratio", "Ratio de sinistres"), ("expense_ratio", "Ratio de frais"),
           ("operating_income", "Résultat net opérationnel"), ("net_income", "Résultat net"))
HELP = {
    "Produits d’assurance": "Produits d’assurance publiés, en milliards de dollars canadiens.",
    "Ratio combiné": "Ratio combiné publié, en pourcentage. Un ratio plus bas est plus favorable.",
    "Ratio de sinistres": "Ratio de sinistres publié, en pourcentage.",
    "Ratio de frais": "Ratio de frais publié, en pourcentage.",
    "Résultat net opérationnel": "Mesure non-IFRS propre à chaque assureur; les ajustements peuvent différer.",
    "Résultat net": "Résultat net publié, en milliards de dollars canadiens.",
}
SCOPE = {company: scope for company, _, scope in COMPANIES}
NEWS_SOURCE_LABELS = {
    "intact_newsroom": "Intact Financial · salle de presse",
    "definity_newsroom": "Definity · salle de presse",
    "aviva_canada_press": "Aviva Canada · communiqués",
    "td_stories_insurance": "TD Stories · TD Insurance",
}


def _news_date(value: Any) -> str:
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else (str(value)[:10] if value else "Date non fournie")


def render_pnc_news(st, articles):
    """Official newsroom items per issuer; context only, never a KPI."""
    st.markdown("<p class='section-eyebrow'>Salles de presse officielles</p>", unsafe_allow_html=True)
    st.caption("Communiqués publiés par les assureurs. Ils apportent du contexte et ne modifient jamais les KPI publiés.")
    names = {company: name for company, name, _ in COMPANIES}
    items = [dict(article, news_kind="Source officielle") for article in articles]
    if not items:
        st.caption("Aucune actualité officielle n’est encore disponible.")
        return
    _kinds, source_options, category_options = news_facets(items, NEWS_SOURCE_LABELS)
    company_column, source_column, category_column = st.columns(3)
    chosen_companies = company_column.multiselect("Assureur", [name for company, name, _ in COMPANIES if any(a["company_id"] == company for a in items)], key="pnc-news-company")
    chosen_sources = source_column.multiselect("Source", source_options, key="pnc-news-source")
    chosen_categories = category_column.multiselect("Catégorie", category_options, key="pnc-news-category")
    if chosen_companies:
        wanted = {company for company, name in names.items() if name in chosen_companies}
        items = [item for item in items if item["company_id"] in wanted]
    items = filter_articles(items, NEWS_SOURCE_LABELS, (), chosen_sources, chosen_categories)
    if not items:
        st.caption("Aucune actualité ne correspond aux filtres choisis.")
    for article in items[:20]:
        metadata = [names.get(article["company_id"], article["company_id"]), NEWS_SOURCE_LABELS.get(article["source"], article["source"])]
        metadata.extend(article.get("categories") or [])
        metadata.append(_news_date(article.get("published_at")))
        st.markdown(f"**{article['title']}**  \n{' · '.join(metadata)}")
        if article.get("summary"):
            st.write(article["summary"])
        st.link_button("Consulter la source ↗", article["source_url"], key=f"pnc-news-{article['article_id']}")


def _kind(row: dict[str, Any]) -> str:
    """Billions for CAD amounts, percent for ratios — drives the shared formatter."""
    return "billion" if row.get("unit") == "CAD_BILLION" else "percent"


def _prior_year_period(period_id: str) -> str | None:
    if len(period_id) == 7 and period_id[4:6] == "-Q":
        return f"{int(period_id[:4]) - 1}{period_id[4:]}"
    return None


def pnc_delta(current_row: dict[str, Any], all_rows) -> str:
    """A year-over-year delta badge, only when the comparison is legitimate.

    Legitimate means: a prior-year same-quarter reviewed observation exists for
    the same company and metric, with the same calendar basis. Otherwise no
    delta is shown. The tone is neutral: favourability differs by metric (a
    lower combined ratio is better), so we never colour the chip green or red.
    """
    prior_period = _prior_year_period(str(current_row.get("period_id", "")))
    if not prior_period:
        return ""
    prior = next(
        (row for row in all_rows
         if row.get("company_id") == current_row.get("company_id")
         and row.get("metric_id") == current_row.get("metric_id")
         and row.get("period_id") == prior_period
         and row.get("calendar_basis") == current_row.get("calendar_basis")),
        None,
    )
    if prior is None or prior.get("value") is None or current_row.get("value") is None:
        return ""
    current_value = float(current_row["value"])
    prior_value = float(prior["value"])
    if _kind(current_row) == "percent":
        change = current_value - prior_value
        text = f"{change:+.1f} pp"
    else:
        if prior_value == 0:
            return ""
        change = (current_value - prior_value) / prior_value * 100
        text = f"{change:+.1f} %"
    symbol = "▲" if change > 0 else "▼" if change < 0 else "•"
    return delta_badge(f"{symbol} {text}", "flat", f"vs {prior_period}")


def pnc_comparison_html(period: str | None, published_rows, all_rows) -> str:
    """Branded comparison table for the reference period, with P&C meta columns."""
    header_cells = [header_cell("Compagnie"), header_cell("Périmètre"),
                    header_cell("Clôture"), header_cell("Calendrier")]
    header_cells += [header_cell(label, HELP.get(label)) for _, label in METRICS]
    body: list[str] = []
    for company, _name, scope in COMPANIES:
        rows = [row for row in published_rows if row["company_id"] == company]
        ends = {str(row["period_end"]) for row in rows}
        if len(ends) > 1:
            raise ValueError("Conflicting published closing dates")
        has_rows = bool(rows)
        calendar = ("Fiscal" if any(row.get("calendar_basis") == "fiscal" for row in rows)
                    else "Civil") if has_rows else "N/A"
        cells = [
            row_header_cell(company, f"{company}.{period}" if has_rows and period else company),
            meta_cell(scope),
            meta_cell(next(iter(ends), "N/A")),
            meta_cell(calendar),
        ]
        for metric, _label in METRICS:
            row = next((r for r in rows if r["metric_id"] == metric), None)
            if row is None:
                cells.append(empty_cell())
                continue
            cells.append(value_cell(
                format_value(row.get("value"), _kind(row)),
                period=period,
                delta_html=pnc_delta(row, all_rows),
            ))
        body.append(row_open(company) + "".join(cells) + "</tr>")
    return table_shell(header_cells, body)


def pnc_history_table(rows):
    """Expose reviewed observations with their true quarter and closing date."""
    companies = {company: (index, name) for index, (company, name, _) in enumerate(COMPANIES)}
    metrics = {metric: (index, label) for index, (metric, label) in enumerate(METRICS)}
    ordered = sorted(
        (row for row in rows if row.get("company_id") in companies and row.get("metric_id") in metrics),
        key=lambda row: (-int(row["period_id"][:4]), -int(row["period_id"][-1]),
                         companies[row["company_id"]][0], metrics[row["metric_id"]][0]),
    )
    return [{"Trimestre": row["period_id"], "Compagnie": companies[row["company_id"]][1],
             "Indicateur": metrics[row["metric_id"]][1],
             "Valeur": format_value(row["value"], "billion" if row["unit"] == "CAD_BILLION" else "percent"),
             "Clôture": str(row["period_end"]),
             "Calendrier": "Fiscal" if row["calendar_basis"] == "fiscal" else "Civil",
             "Rapport officiel": row["source_url"]} for row in ordered]


def render_pnc_preview(st, published_rows=(), operations_alerts=(), acquisition=None, news=None):
    from pnc_data import current_pnc_rows
    all_rows = list(published_rows)
    period, published_rows = current_pnc_rows(all_rows)
    st.markdown(
        vigie_header("Assurance de dommages · Canada", "Vigie de l'industrie",
                     "IFC · AV · TD · DFY — résultats et actualités"),
        unsafe_allow_html=True,
    )
    coverage = pnc_sources([(company, name) for company, name, _ in COMPANIES], published_rows, all_rows, period)
    sections = [SidebarSection("Assureurs de dommages", f"{sum(row.level == 'ok' for row in coverage)} / {len(COMPANIES)}",
                               f"Période de référence : {period}" if period else None, coverage)]
    if acquisition is not None:
        attempts, audit = acquisition
        steps = pnc_acquisition_rows([company for company, _name, _scope in COMPANIES],
                                     {row["company_id"]: row for row in attempts}, audit)
        sections.append(SidebarSection("Acquisition", None, None, steps))
    if news is not None:
        news_articles, news_counts, news_audit = news
        news_status = pnc_news_rows([company for company, _name, _scope in COMPANIES],
                                    {row["company_id"]: row for row in news_counts}, news_audit, datetime.now(UTC))
        sections.append(SidebarSection("Actualités officielles", f"{news_audit['sources_succeeded']} / {len(COMPANIES)}" if news_audit else None,
                                       None, news_status))
    render_sidebar(st, sections, alert_rows(operations_alerts))
    st.caption("Intact Financial · Aviva Canada · TD Insurance · Definity Financial")
    if not published_rows:
        st.info("Les données P&C sont en cours de validation. Aucun KPI n’est encore publié dans cette vue.")
    else:
        st.caption(f"Période de référence : {period}. Les dates de clôture peuvent différer selon l’assureur.")
        if len({row["period_end"] for row in published_rows}) > 1:
            closes = [(name, sorted({str(row["period_end"]) for row in published_rows
                                     if row["company_id"] == company}))
                      for company, name, _ in COMPANIES]
            details = "; ".join(f"{name} : {', '.join(dates)}" for name, dates in closes if dates)
            st.warning(f"Attention : les périodes de clôture diffèrent ({details}). "
                       "Les trimestres fiscaux et civils ne couvrent pas les mêmes dates.")
    labels = ["Synthèse", "Historique validé"] if news is None else ["Synthèse", "Actualités", "Historique validé"]
    opened = st.tabs(labels)
    summary_tab, history_tab = opened[0], opened[-1]
    if news is not None:
        with opened[1]:
            render_pnc_news(st, news[0])
    with summary_tab:
        st.markdown("<p class='section-eyebrow'>Comparatif en un coup d'œil</p>", unsafe_allow_html=True)
        st.subheader("Résultats des quatre compagnies")
        st.caption("Une variation annuelle n’est affichée que si le même trimestre de l’année précédente "
                   "existe pour le même assureur et le même calendrier.")
        st.markdown(pnc_comparison_html(period, published_rows, all_rows), unsafe_allow_html=True)
        if published_rows and not any(row["company_id"] == "AV" for row in published_rows):
            st.info("Aviva Canada : un rapport HY 2026 est disponible, mais son ratio combiné couvre six mois. Il reste N/A dans la comparaison trimestrielle; aucun T2 canadien isolé n’a été validé.")
            st.link_button("Voir le rapport semestriel officiel d’Aviva Canada", AVIVA_HY26_URL,
                           key="pnc-aviva-hy26-source")
        st.caption("Le résultat net opérationnel est une mesure non-IFRS propre à chaque assureur; ses ajustements peuvent différer. Vérifiez le rapport officiel avant une comparaison directe.")
        for company, name, _ in COMPANIES:
            sources = sorted({row["source_url"] for row in published_rows if row["company_id"] == company})
            for index, url in enumerate(sources):
                st.link_button(f"Rapport officiel — {name}", url, key=f"pnc-source-{company}-{index}")
    with history_tab:
        if len({row["period_id"] for row in all_rows}) > 1:
            st.subheader("Historique trimestriel validé")
            st.caption("Chaque ligne conserve sa clôture et son calendrier. Les trimestres fiscaux de TD ne couvrent pas les mêmes dates que les trimestres civils.")
            st.dataframe(
                pnc_history_table(all_rows), hide_index=True, width="stretch",
                column_config={"Rapport officiel": st.column_config.LinkColumn(
                    "Rapport officiel", display_text="Ouvrir")},
            )
        else:
            st.info("L’historique s’affichera dès que plusieurs trimestres validés seront publiés.")
    st.caption("N/A signifie ici qu’aucune valeur validée n’a été publiée, et non que l’assureur n’a pas communiqué de résultat.")
    st.subheader("Périmètres et périodes")
    st.write("Les résultats consolidés d’Intact et de Definity ne représentent pas le même périmètre que les segments Aviva Canada et TD Insurance.")
    st.write("Les résultats semestriels, les cumuls annuels et les rendements sur douze mois seront distingués des résultats du trimestre.")
