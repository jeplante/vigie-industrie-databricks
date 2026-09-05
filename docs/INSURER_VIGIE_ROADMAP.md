# Feuille de route - Vigie assurance de personnes dans Databricks

**Statut :** Slices 10 a 14 integrees localement; acceptation Databricks et acquisition live en attente
**Date :** 2026-09-04
**But produit :** transposer dans Databricks la vigie des quatre grands
assureurs de personnes canadiens : Manuvie (MFC), Sun Life (SLF),
Great-West Lifeco (GWO) et iA Groupe financier (IAG).

## 1. Etat de depart et cible

Les Slices 0 a 9 ont etabli une base Databricks saine : tables Delta,
transformations Finance Bronze/Silver/Gold, App en lecture seule, Job News,
acquisition de contexte Statistique Canada et enrichissement IA natif borne.

La partie Finance reste cependant une fondation de migration : le Job Finance
accepte seulement `input_mode=fixture`, et les observations ne portent pas
encore le document officiel, l'unite, la qualite, la fraicheur ou la politique
de metrique du produit Vigie original.

La cible est une application qui permet de comparer les resultats publies de
MFC, SLF, GWO et IAG, de remonter chaque chiffre a sa source officielle et de
consulter leurs actualites officielles, completees explicitement par le
contexte Statistique Canada. Le navigateur ne doit jamais contacter une source
assureur ni lancer une acquisition.

### Etat implemente de Slice 10

Les fichiers `config/companies.yaml`, `config/metrics.yaml` et
`config/sources.yaml` etablissent maintenant les quatre societes cibles, 13 KPI
initiaux et une source officielle allowlistee par societe. Le module
`vigie_databricks.insurer_contract` charge et valide ces contrats ainsi que les
candidats d'observation representatifs. La fixture Slice 10 couvre les quatre
societes et plusieurs types de periode.

Le contrat implemente propose `FINANCIAL_DOCUMENT_SCHEMA` et
`FINANCE_RUN_AUDIT_SCHEMA`. Il conserve les metadonnees de provenance, les
empreintes, ETag, Last-Modified, statuts et raisons d'echec; aucun contenu brut
n'est persiste par ce contrat. La decision de retention reste requise avant une
table de contenu ou un run live.

### Etat implemente de Slice 11

Le module `vigie_databricks.finance_acquisition` effectue une lecture HTTPS
bornee d'un document Finance deja identifie. Il applique l'allowlist par
societe, 20 secondes de timeout par defaut, 15 MB maximum, types PDF/HTML
attendus et requetes conditionnelles ETag/Last-Modified. Une reponse HTTP 304
preserve l'empreinte connue sans telecharger le contenu. Les tests utilisent des
reponses simulees : aucun assureur n'a ete contacte.

Il reste a implementer la decouverte specifique a chaque assureur, la persistence
Delta et les resultats isoles par source. Ces etapes exigent l'approbation des
sources et de la retention avant tout acces live.

## 2. Principes non negociables

- Une valeur financiere publiee provient d'une source primaire officielle ou
  reste absente; une actualite secondaire ne peut pas la remplacer.
- Une acquisition ou une extraction en erreur ne remplace jamais le dernier
  resultat valide : l'etat devient `stale` ou `unknown` avec une raison.
- Les identifiants stables sont `company_id`, `metric_id` et `period_id`.
  `period_id` doit etre composite, par exemple `2026-Q1`; une periode ne peut
  pas en ecraser une autre.
- Les appels IA sont un secours trace pour les documents ambigus, jamais la
  source de verite des valeurs, et restent soumis a une validation stricte.
- Les sources, seuils, metriques et societes sont versionnes. Aucun URL ou
  parametre de source ne vient de l'App.
- Les Jobs restent idempotents, les tables de test UUID restent nettoyees, et
  l'App conserve des privileges de lecture seuls.

## 3. Slices proposees

### Slice 10 - Contrat de vigie assurance et migration de configuration

**Objectif :** etablir le contrat metier commun avant toute acquisition live.

**Inclure :**

- migrer et valider la configuration versionnee des quatre assureurs, des KPI,
  des unites, des tendances favorables et des sources officielles depuis
  `vigie_industrie`;
- definir le contrat de periode complet : annee, trimestre, date de fin,
  libelle et `period_id` stable;
- definir les contrats de provenance et qualite : URL, type de document,
  empreinte, date de publication, date de controle, methode d'extraction,
  avertissements et statut de fraicheur;
- concevoir les nouvelles tables de documents et d'audit Finance sans casser
  `bronze_observations`, `silver_observations` ni `gold_observations`;
- ajouter des fixtures representant les quatre assureurs et plusieurs
  periodes, y compris un KPI absent et une source non joignable.

**Ne pas inclure :** acces reseau, modification du schedule, appel IA ou
refonte de l'App.

**Sortie :** schemas versionnes et tests de validation du contrat; les donnees
fixture peuvent representer fidelement MFC, SLF, GWO et IAG.

### Slice 11 - Decouverte et acquisition bornee des documents financiers

**Objectif :** remplacer l'entree fixture par une decouverte officielle,
configurable et observable, sans encore extraire de KPI.

**Inclure :**

- un adaptateur par assureur pour ses pages investisseurs et documents
  financiers officiels;
- HTTPS, allowlist par assureur, timeout, reprises bornees, redirections
  controlees, limites de taille et journal par source;
- ETag, Last-Modified et SHA-256 pour eviter les telechargements inutiles;
- une table Bronze de documents avec metadonnees, empreinte, resultat de
  controle et emplacement de contenu brut conforme a la politique de retention;
- une execution `dry-run` sans ecriture durable et des fixtures HTTP/PDF/HTML
  pour tous les adaptateurs.

**Decision humaine avant run live :** valider les URLs, conditions d'usage,
retention du contenu brut et solution autorisee pour les sources qui bloquent
les clients automatises.

**Sortie :** chaque assureur produit un resultat explicite `current`, `stale`
ou `unknown`; aucun echec de source ne corrompt une table publiee.

### Slice 12 - Extraction deterministe des KPI financiers

**Objectif :** extraire les KPI des documents officiels de maniere explicable.

**Inclure :**

- parseurs PDF/HTML limites aux selecteurs, tableaux et alias configures par
  assureur et metrique;
- normalisation des unites, devises, signes, periodes et identifiants
  `COMPANY-YEAR-PERIOD-METRIC`;
- ecriture des candidats avec reference au document, emplacement extrait et
  methode d'extraction;
- couverture de fixtures pour les formats publies courants, les valeurs
  ambigues et les documents incomplets;
- rejet explicite plutot que valeur inventee lorsqu'une extraction est
  incomplete ou incoherente.

**Ne pas inclure :** modele de langage, publication automatique ou changement
de l'interface.

**Sortie :** des observations Finance candidates issues des quatre assureurs
peuvent alimenter Bronze avec une provenance complete et reproductible.

### Slice 13 - Validation, fraicheur et publication Finance atomique

**Objectif :** convertir les candidats en jeu de donnees fiable pour le produit.

**Inclure :**

- regles Silver pour identifiants, nombres finis, unites attendues, periodes,
dates, source primaire, doublons et seuils de variation;
- calcul de comparaison avec uniquement la meme periode de l'annee precedente;
- statut par assureur : derniere periode disponible, derniere periode publiee,
dernier controle et fraicheur `current`, `stale` ou `unknown`;
- rapport de qualite, table d'audit Finance et publication atomique de la vue
Gold apres validation de l'ensemble;
- conservation du dernier Gold valide lorsqu'un nouveau document est
inexploitable.

**Sortie :** `gold_observations` devient une vue comparable, sourcee et
last-known-good des quatre assureurs; le Job Finance n'utilise plus la fixture
en production.

### Slice 14 - Secours IA structure pour extraction financiere

**Objectif :** traiter seulement les documents dont l'extraction deterministe
est insuffisante, sans diminuer les exigences de qualite.

**Inclure :**

- un contrat JSON strict specifique a un KPI, une periode et un document deja
  identifies;
- le fournisseur Databricks Model Serving existant comme choix par defaut, ou
  une decision explicite si le projet doit conserver le fournisseur OpenAI de
  `vigie_industrie`;
- contenu tronque, sortie bornee, budget par run, mode sans IA et raisons
  d'echec distinctes;
- trace par resultat : fournisseur, modele, prompt, empreinte source, usage,
  avertissements et methode d'extraction;
- validation identique aux valeurs deterministes et tests sans appel reel.

**Ne pas inclure :** estimation, rapprochement comptable automatique ou
publication d'une valeur qui echoue a la validation.

**Sortie :** une valeur IA n'est publiable que si elle est tracee et satisfait
toutes les regles de la Slice 13; sinon le dernier resultat valide reste servi.

### Slice 15 - Actualites officielles des assureurs

**Objectif :** faire de la section News une vigie des assureurs et non seulement
un contexte macroeconomique.

**Inclure :**

- ajouter les flux ou pages officielles de news/communiques de MFC, SLF, GWO et
  IAG avec les memes garde-fous que les sources Statistique Canada;
- conserver `source_type` et `company_id` afin de distinguer une actualite
  entreprise d'un contexte Statistique Canada;
- dedupliquer par URL canonique et empreinte, et relier une actualite a zero,
  une ou plusieurs societes avec provenance;
- reemployer le contrat IA News borne existant pour resume et categorisation,
  sans rendre le resume obligatoire a la publication de l'article.

**Sortie :** Gold News permet les filtres par assureur, source et categorie et
affiche toujours le lien vers la publication originale.

### Slice 16 - Experience de vigie dans l'App Databricks

**Objectif :** exposer le produit de surveillance sans donner de capacite
operationnelle a l'utilisateur final.

**Inclure :**

- selection de compagnie et de periode publiee, avec comparaison inter-assureur
et historique limite a la retention approuvee;
- KPI accompagnes de leur unite, tendance, date de publication, lien source et
indicateur de fraicheur;
- fil News separant actualites officielles des assureurs et contexte externe;
- etats clairs pour donnees absentes, `stale`, `unknown`, echec partiel et
audit IA; export des observations Gold publiees si besoin valide;
- tests d'acces garantissant que le service principal reste `SELECT` only.

**Sortie :** l'App repond a la question produit : comment chaque assureur se
compare, quelles donnees sont a jour et quelles actualites officielles meritent
attention.

### Slice 17 - Orchestration, exploitation et passage en production

**Objectif :** planifier et operer le produit avec un cout et un risque bornes.

**Inclure :**

- separer clairement la cadence de decouverte Finance de la cadence News;
- commencer Finance par une verification quotidienne des sources, mais ne
  publier une nouvelle periode qu'apres validation; conserver News toutes les
  six heures tant que le volume et le cout le justifient;
- alertes sur echec de source, `stale`, `unknown`, budget IA, absence de
  publication attendue et echec de reconciliation;
- tableau de bord des volumes, durees, appels/tokens IA et couts Databricks
  issus des donnees de facturation disponibles;
- runbooks de rollback : pause de schedule, reprise d'une source, restauration
  last-known-good et rotation des secrets;
- CI sur tests unitaires et Databricks Connect. La decision d'utiliser GitHub
  Actions pour ce depot est explicite et n'est pas implicite dans le code.

**Sortie :** Jobs, couts, qualite et reprise sont exploitables sans intervention
manuelle quotidienne et avec un rollback documente.

## 4. Ordre et gates

`10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17`

Les Slices 10 a 13 forment le chemin critique Finance. La Slice 14 ne demarre
qu'apres mesure des erreurs de la Slice 12; elle peut etre omise si les
extracteurs deterministes couvrent le besoin. La Slice 15 peut avancer en
parallele de la Slice 13 une fois le contrat de source de la Slice 10 accepte.
La Slice 16 depend des tables Gold et statuts de fraicheur; la Slice 17 n'active
la cadence de production qu'apres une periode d'observation manuelle reussie.

Avant chaque mise en production live : tests locaux, tests Databricks Connect,
run borne, rerun idempotent, reconciliation des tables, verification des droits
et revue des couts. Chaque slice met a jour le README et le handoff avec les
ressources deployees, les decisions prises et les limites connues.

## 5. Decisions a prendre avant Slice 10

Decisions confirmees le 4 septembre 2026 :

- conserver les quatre assureurs et les 13 KPI initiaux;
- conserver le contenu brut 365 jours dans
  `/Volumes/workspace/vigie/finance_raw`;
- n'autoriser que les domaines officiels versionnes dans `sources.yaml`;
- utiliser Databricks Model Serving pour le secours IA, avec un maximum de
  10 appels par run;
- publier initialement dans l'App Databricks seulement;
- garder le reseau live desactive par defaut jusqu'au gate d'acceptation.

Les questions ci-dessous sont donc closes pour la premiere mise en production;
elles devront etre rouvertes explicitement si la portee change.

1. Confirmer la liste initiale des KPI publies et les unites attendues pour les
   quatre assureurs.
2. Choisir la retention du contenu PDF/HTML brut et son emplacement Databricks.
3. Autoriser explicitement une source secondaire officielle lorsqu'un assureur
   bloque l'acces automatise a sa page investisseurs.
4. Confirmer que Databricks Model Serving remplace OpenAI pour le secours
   Finance, ou approuver OpenAI et son secret comme exception controlee.
5. Choisir la destination de production : App Databricks seule ou export
   supplementaire vers GitHub Pages/SharePoint.
