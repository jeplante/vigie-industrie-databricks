# Statistique Canada - 6 septembre 2026

Le Job Actualites `1118291153119927` est converti en Job
`vigie-official-investor-news`; il reste en pause pendant sa validation. Aucun
run Statistique Canada n'etait actif lors du controle. Son parametre
`sources_json` est maintenant `[]`; les flux Fabrication et Commerce
international ont ete retires. Le template legacy local utilise la meme
configuration. Le Job Finance est inchange.

Les tables et audits existants sont conserves. L'App filtre les articles sur
les domaines officiels des quatre assureurs; Statistique Canada n'est plus
une source presentee. Les archives ne sont pas supprimees.

Les sources officielles sont Manuvie (communique PDF des resultats accessible
directement), Sun Life, Great-West Lifeco et iA. Le dry-run 4/4 puis deux runs
persistants ont reussi: 10 communiques, aucun appel IA; le second run n'a fait
ni insertion ni mise a jour. Le schedule reste en pause jusqu'au raccordement
de l'App et a sa revue visuelle.

La collecte historique est separee de la publication des KPI :
`scripts/fetch_finance_history.py` conserve les PDF et leur provenance dans
le volume Finance et `financial_documents`, mais ne publie pas les valeurs
extraites. Les archives Sun Life, les pages trimestrielles Great-West et les
communiques T4 Manuvie completent la decouverte courante. Les 72 periodes,
de T1 2022 a T2 2026 pour chaque assureur, ont un PDF brut conserve. La revue
produit des candidats controles par empreinte. Les periodes deja referencees
avec un fichier brut sont ignorees lors de la reprise.

## Publication de l'historique - 7 septembre 2026

Le Job `vigie-finance-history-publish` (`623558766235360`) valide les candidats
contre leur document source avant toute publication. Le passage de validation
retient uniquement les rapports trimestriels dont la compagnie, la periode,
l'URL et l'empreinte correspondent au document indexe. Pour la publication
initiale jusqu'a T4 2025, 230 observations trimestrielles ont ete validees et
4 candidats ont ete rejetes; 36 candidats hors plage ou non trimestriels sont
conserves pour revue, sans etre publies.

Le premier run persistant a insere 229 observations et mis a jour 1
observation dans Bronze/Silver, puis a mis a jour 18 cles et insere 3 cles
dans Gold. La reconciliation Bronze/Silver/Gold est nulle. Le second run
persistant a reussi avec 0 insertion et 0 mise a jour dans les trois couches,
ce qui confirme l'idempotence. Le Job est intentionnellement non planifie :
il s'agit d'une reprise historique ponctuelle. Le Job Finance live quotidien
reste la seule publication planifiee.
