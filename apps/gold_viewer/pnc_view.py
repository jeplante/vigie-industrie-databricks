"""P&C landing page backed exclusively by reviewed Gold observations.

Slice 18 brings the P&C universe onto the shared visual system (branded header,
brand-colour comparison table, period chips, tooltips, single value formatter)
while keeping every P&C domain guardrail: the Périmètre / Clôture / Calendrier
columns, the divergent-close warnings, the `N/A` semantics, and a year-over-year
delta only when a same-calendar, same-quarter prior-year value exists.
"""
from __future__ import annotations

from typing import Any

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


def render_pnc_preview(st, published_rows=()):
    from pnc_data import current_pnc_rows
    all_rows = list(published_rows)
    period, published_rows = current_pnc_rows(all_rows)
    st.markdown(
        vigie_header("Assurance de dommages · Canada", "Vigie de l'industrie",
                     "IFC · AV · TD · DFY — résultats et actualités"),
        unsafe_allow_html=True,
    )
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
    if len({row["period_id"] for row in all_rows}) > 1:
        st.subheader("Historique trimestriel validé")
        st.caption("Chaque ligne conserve sa clôture et son calendrier. Les trimestres fiscaux de TD ne couvrent pas les mêmes dates que les trimestres civils.")
        st.dataframe(
            pnc_history_table(all_rows), hide_index=True, width="stretch",
            column_config={"Rapport officiel": st.column_config.LinkColumn(
                "Rapport officiel", display_text="Ouvrir")},
        )
    st.caption("N/A signifie ici qu’aucune valeur validée n’a été publiée, et non que l’assureur n’a pas communiqué de résultat.")
    st.subheader("Périmètres et périodes")
    st.write("Les résultats consolidés d’Intact et de Definity ne représentent pas le même périmètre que les segments Aviva Canada et TD Insurance.")
    st.write("Les résultats semestriels, les cumuls annuels et les rendements sur douze mois seront distingués des résultats du trimestre.")
