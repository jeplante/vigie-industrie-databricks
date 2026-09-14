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
communiques T4 Manuvie completent la decouverte courante. La reprise cible les
72 periodes, de T1 2022 a T2 2026 pour les quatre assureurs. Une periode n'est
consideree acquise que si son fichier brut provient d'un rapport aux
actionnaires, d'un rapport financier ou d'un communique de resultats admissible.
Les transcriptions, presentations et certificats restent dans l'audit, mais ne
peuvent plus satisfaire la couverture ni alimenter un KPI.

## Publication de l'historique - mise a jour du 14 septembre 2026

Le Job `vigie-finance-history-publish` (`623558766235360`) valide les candidats
contre leur document source avant toute publication. Le passage de validation
retient uniquement les rapports trimestriels dont la compagnie, la periode,
l'URL et l'empreinte correspondent au document indexe. Il verifie aussi le KPI
attendu, l'unite, les bornes de valeur, le contexte comptable, la completude de
chaque compagnie-periode et les variations annuelles extremes. Un KPI absent
reste `N/A`; une valeur suspecte reste en quarantaine avec sa raison sans faire
disparaitre les autres KPI valides du trimestre. La derniere publication fiable
est preservee et les versions Delta precedentes sont restaurees si la
publication multi-couche echoue.

Le dry-run `925379669030111` a revu 399 candidats issus de 72 rapports, sans
erreur d'extraction. Il a valide 392 observations, mis 7 valeurs anormales en
quarantaine et releve 12 compagnie-periodes incompletes; les KPI absents restent
`N/A`. Le T2 2025 est complet pour les quatre assureurs, notamment le BPA de
Great-West Lifeco a 1,24 $.

La publication `943155556729120` a retire 9 anciennes observations ou donnees
de demonstration, puis publie les 392 valeurs valides avec une reconciliation
nulle entre Bronze, Silver et Gold. Le second run persistant
`1109043667602846` n'a fait aucune insertion, mise a jour ou suppression dans
les trois couches, ce qui confirme l'idempotence. Le Job reste
intentionnellement non planifie : il s'agit d'une reprise historique ponctuelle.
Le Job Finance live quotidien reste la seule publication planifiee.
