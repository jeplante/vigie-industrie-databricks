"""P&C landing page backed exclusively by reviewed Gold observations."""

COMPANIES = (
    ("IFC", "Intact Financial", "Groupe consolidé"),
    ("AV", "Aviva Canada", "Segment Canada"),
    ("TD", "TD Insurance", "Activités d’assurance"),
    ("DFY", "Definity Financial", "Groupe consolidé"),
)


def render_pnc_preview(st, published_rows=()):
    from pnc_data import current_pnc_rows
    period, published_rows = current_pnc_rows(published_rows)
    st.title("Assurance de dommages")
    st.caption("Intact Financial · Aviva Canada · TD Insurance · Definity Financial")
    if not published_rows:
        st.info("Les données P&C sont en cours de validation. Aucun KPI n’est encore publié dans cette vue.")
    else:
        st.caption(f"Période de référence : {period}. Les dates de clôture peuvent différer selon l’assureur.")
        if len({row["period_end"] for row in published_rows}) > 1:
            st.warning("Attention : TD Insurance utilise un trimestre fiscal clos le 30 avril; les résultats publiés ici pour Intact et Definity sont clos le 30 juin. Ces valeurs ne couvrent pas les mêmes dates.")
    st.subheader("Résultats des quatre compagnies")
    table = []
    metrics = (("insurance_revenue", "Produits d’assurance"), ("combined_ratio", "Ratio combiné"),
               ("claims_ratio", "Ratio de sinistres"), ("expense_ratio", "Ratio de frais"),
               ("operating_income", "Résultat opérationnel"), ("net_income", "Résultat net"))
    for company, name, scope in COMPANIES:
        rows = [row for row in published_rows if row["company_id"] == company]
        ends = {str(row["period_end"]) for row in rows}
        if len(ends) > 1:
            raise ValueError("Conflicting published closing dates")
        output = {"Compagnie": name, "Périmètre": scope,
                  "Période publiée": period if rows else "N/A",
                  "Clôture": next(iter(ends), "N/A"),
                  "Calendrier": "Fiscal" if any(row["calendar_basis"] == "fiscal" for row in rows) else "Civil" if rows else "N/A"}
        for metric, label in metrics:
            row = next((r for r in rows if r["metric_id"] == metric), None)
            output[label] = (f"{row['value']:.3f} G$ CA" if row["unit"] == "CAD_BILLION"
                             else f"{row['value']:.1f} %") if row else "N/A"
        table.append(output)
    st.dataframe(table, hide_index=True, width="stretch")
    for company, name, _ in COMPANIES:
        sources = sorted({row["source_url"] for row in published_rows if row["company_id"] == company})
        for index, url in enumerate(sources):
            st.link_button(f"Rapport officiel — {name}", url, key=f"pnc-source-{company}-{index}")
    st.caption("N/A signifie ici qu’aucune valeur validée n’a été publiée, et non que l’assureur n’a pas communiqué de résultat.")
    st.subheader("Périmètres et périodes")
    st.write("Les résultats consolidés d’Intact et de Definity ne représentent pas le même périmètre que les segments Aviva Canada et TD Insurance.")
    st.write("Les résultats semestriels, les cumuls annuels et les rendements sur douze mois seront distingués des résultats du trimestre.")
