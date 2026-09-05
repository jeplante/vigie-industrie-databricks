# PROJECT HANDOFF - vigie-industrie-databricks

**Mise a jour : 2026-09-04 (America/Toronto)**
**Repo :** `C:\Users\jerom\vigie_databricks`
**GitHub :** `jeplante/vigie-industrie-databricks`
**Branche / HEAD de reference :** `main` / `c5057cb` avant integration locale Finance 0.5.0

> **ETAT VERIFIE.** Les Slices 7 et 8 sont commitees et poussees. Le depot est propre et `main` est synchronisee avec `origin/main`. Le critere des lignes differees de la Slice 8 a ete verifie le 4 septembre 2026 sur le run `937246177868747`.

## 1. Objectif

Ce fichier est la memoire technique canonique du projet. Il permet a une nouvelle tache Codex, ChatGPT ou GitHub Copilot de reprendre sans reconstruire les decisions des Slices 0 a 6.

Le projet combine un pipeline financier Bronze/Silver/Gold, une App Databricks Streamlit en lecture seule et un pipeline News avec enrichissement IA natif Databricks.

## 2. Etat des Slices

| Slice | Resultat | Git |
|---|---|---|
| 0 - Fondation | Terminee et validee | `d6a2146` |
| 1 - Bronze | Terminee, durcie, validee | `bc28df3` |
| 2 - Silver | Terminee et validee | `035a6b6` |
| 3 - Gold | Terminee et validee | `96aafa9` |
| 4 - Job financier | Terminee et validee | `2933dc1` |
| 5 - App + Unity Catalog | Terminee et validee | `d7971d1` |
| 6 - News + IA | Terminee, validee, poussee | `1135f73` |
| 7 - News live | Terminee et validee | `32a9e5b` |
| 8 - Observabilite IA | Terminee et validee | `b492753` |
| 9 - Fiabilite sorties IA | Terminee et validee | `HEAD` |
| 10 - Contrat vigie assurance | Integre localement, politique produit versionnee | travail courant 0.5.0 |
| 11 - Acquisition documents Finance | Retrieval borne teste hors ligne; live non active | travail courant 0.5.0 |
| 12 - Extraction deterministe | Integree localement; fixtures seulement | travail courant 0.5.0 |
| 13 - Publication atomique | Point d'entree, audit et last-known-good integres localement | travail courant 0.5.0 |
| 14 - Secours IA Finance | Contrat local Databricks Model Serving; appel live non valide | travail courant 0.5.0 |
| 15 a 17 - News assureurs a exploitation | Non commencees | - |

Le commit Slice 6 porte le message peu descriptif `update`, mais contient exactement les 20 chemins attendus : 586 insertions et 4 suppressions. La Slice 8 arrive via deux commits au message identique (`3f59d0b`, `d16e550`) reconcilies par le merge `b492753`. Ne pas reecrire l'historique pour renommer ces commits.

## 3. Architecture durable

```text
Donnees financieres
  -> workspace.vigie.bronze_observations
  -> workspace.vigie.silver_observations
  -> workspace.vigie.gold_observations
  -> App Streamlit (lecture seule)

News
  -> workspace.vigie.bronze_news
  -> workspace.vigie.silver_news
  -> workspace.vigie.news_ai_enrichment (audit : workspace.vigie.news_ai_run_audit)
  -> workspace.vigie.gold_news
  -> section News de l'App (lecture seule)
```

Principes :

- logique metier dans `src/vigie_databricks`;
- points d'entree de taches minces;
- tables durables dans `workspace.vigie`;
- objets de tests isoles par UUID et supprimes au teardown;
- Jobs Finance et News independants;
- App strictement read-only;
- modele IA configurable et appels idempotents;
- appels modele plafonnes par run (`max_model_calls`, defaut 10) et audites par `job.run_id`;
- aucun secret OpenAI externe.

## 4. Environnement local

- Repo cible : `C:\Users\jerom\vigie_databricks`.
- Ancien repo : `C:\Users\jerom\vigie_industrie`, lecture seule.
- Python cible : 3.12.
- Profil Databricks : `jeplante`.
- CLI disponible dans l'extension VS Code Databricks.
- Warehouse : Serverless Starter Warehouse, ID `9afffea8b155f79d`.
- App : `vigie-gold-viewer`.
- Databricks Connect est le gate Spark/Delta principal.
- Java/Spark local reste optionnel.

## 5. Objets et ressources Databricks

### Unity Catalog

Objets financiers :

- `workspace.vigie.bronze_observations`;
- `workspace.vigie.silver_observations`;
- `workspace.vigie.gold_observations`.

Objets News :

- `workspace.vigie.bronze_news`;
- `workspace.vigie.silver_news`;
- `workspace.vigie.news_ai_enrichment`;
- `workspace.vigie.news_ai_run_audit`;
- `workspace.vigie.gold_news`.

Comptes confirmes le 4 septembre : Finance 3/3/2; News 45/45/45/45.

### Jobs

Job financier :

- nom versionne : `vigie-slice4-bronze-silver-gold`;
- ID : `319208446632488`;
- template : `databricks_slice4_job.template.json`;
- chaine : Bronze -> Silver -> Gold.

Job News :

- nom : `vigie-slice6-news-ai`;
- ID : `1118291153119927`;
- template : `databricks_slice6_news_job.template.json`;
- chaine : Bronze News -> Silver News -> IA -> Gold News;
- schedule actif : `0 0 0/6 * * ?` (`America/Toronto`), UNPAUSED;
- budget IA : `max_model_calls=10`, audit `workspace.vigie.news_ai_run_audit`;
- wheel deploye : `vigie_databricks_foundation-0.4.0-py3-none-any.whl`.

### App

- nom : `vigie-gold-viewer`;
- URL connue : `https://vigie-gold-viewer-7474651721951651.aws.databricksapps.com`;
- resource binding : `sql_warehouse`;
- configuration versionnee : `workspace.vigie.gold_observations` et `workspace.vigie.gold_news`;
- panneau sante read-only du dernier audit IA (`workspace.vigie.news_ai_run_audit`);
- service principal : `app-338nse vigie-gold-viewer`
  (`c3560961-d1b6-4253-8b9a-d299f857f393`);
- privileges read-only verifies : `USE_SCHEMA` sur `workspace.vigie` et
  `SELECT` sur `gold_observations`, `gold_news` et `news_ai_run_audit`;
- aucun pipeline declenche par l'App.

## 6. Slices 0 a 6

### Slice 0 - Fondation

Squelette du repo, package Python, `pyproject.toml`, `databricks.yml`, architecture et tests. Decision : petites slices, notebooks minces et logique dans le package.

### Slice 1 - Bronze

Ingestion Delta idempotente, deduplication et audit. Le hardening a distingue idempotence d'etat et no-op operationnel : un rerun identique produit zero insertion et zero mise a jour.

### Slice 2 - Silver

Normalisation et validation Bronze -> Silver, protegee par tests unitaires et Databricks Connect.

### Slice 3 - Gold

Mart comparatif deterministe par entreprise et metrique : periodes/valeurs courantes et precedentes, changements, direction et audit.

### Slice 4 - Job financier

Orchestration native Bronze -> Silver -> Gold. Les anciens objets `workspace.default.vigie_slice4_*` ont ete remplaces par le contrat durable en Slice 5.

### Slice 5 - App et housekeeping

App Streamlit en lecture seule via SQL Warehouse. Creation de `workspace.vigie`, migration vers les objets durables et cleanup automatique des tables de test UUID. Cause racine traitee : accumulation d'objets de tests dans `workspace.default`.

### Slice 6 - News et IA

Acceptance sur fixture RSS de deux articles. Pipeline Bronze/Silver/IA/Gold News. Endpoint natif `databricks-gpt-oss-20b`, sortie JSON stricte, validation stricte et provenance conservee.

Identite d'enrichissement : `article_id + content_hash + prompt_version + model_name`. Un rerun identique a produit `model_calls=0`.

Derniers gates connus :

- 25 tests locaux;
- 9 tests Databricks Connect;
- Job News SUCCESS;
- App RUNNING et HTTP 200;
- comptes financiers inchanges;
- modules financiers `bronze.py`, `silver.py`, `gold.py` inchanges;
- aucun secret externe ni dependance OpenAI.

### Slice 7 - News live

Deux feeds Atom du Quotidien de Statistique Canada (Fabrication, Commerce
international), acquisition bornee a 25 articles par source et par run,
schedule 6 h actif. Contrat IA `slice7-news-enrichment-v2`. Details et
acceptation dans `docs/SLICE7_PLAN.md`.

### Slice 8 - Observabilite et budget IA

Budget dur `max_model_calls=10` par run, selection deterministe par
`article_id`, statut `budget_deferred` sans appel modele, table d'audit
`workspace.vigie.news_ai_run_audit` (une ligne idempotente par `job.run_id`)
et panneau sante read-only dans l'App. Wheel `0.4.0`. Details dans
`docs/SLICE8_PLAN.md`.

Derniers gates connus :

- acceptation budget zero : run `433107641891201`, 0 appel, 43 succes
  conserves, 2 lignes differees;
- traitement progressif des differees : run manuel `937246177868747` du
  2026-09-04, `model_calls=2` sur budget 10, 43 succes non retraites,
  0 ligne differee restante, tables reconciliees a 45;
- la cause des 2 `invalid_output` recurrents est diagnostiquee et corrigee
  en Slice 9 (voir `docs/SLICE9_PLAN.md`).

## 7. Verification Databricks du 3 septembre 2026

Confirme :

- `HEAD` et `origin/main` = `1135f73`;
- arbre de travail propre avant ajout de la documentation;
- commit Slice 6 contient les 20 fichiers attendus;
- les deux Jobs existent avec leurs bons noms, parametres et objets durables;
- dernier run du Job financier : `SUCCESS`;
- dernier run du Job News : `SUCCESS`;
- Job News sans schedule;
- les sept tables Delta managees existent;
- comptes Finance 3/3/2 et News 2/2/2/2;
- App `vigie-gold-viewer` presente avec le bon Warehouse et la bonne URL;
- Warehouse `9afffea8b155f79d` present.

Etat d'exploitation :

- Warehouse `STOPPED` par auto-stop, zero session active;
- App `UNAVAILABLE`, compute `STOPPED`, message : arret en raison du statut workspace/account;
- aucun Job, App, Warehouse ou modele n'a ete demarre pendant le gate;
- un smoke UI demandera un redemarrage explicite de l'App et possiblement du Warehouse.

## 7.1 Verification Databricks du 4 septembre 2026

Confirme :

- run manuel du Job News `937246177868747` : `SUCCESS`;
- audit : `model_calls=2` <= `max_model_calls=10`, `deferred_rows=0`;
- les 2 lignes `budget_deferred` de l'acceptation budget zero ont ete
  traitees (statut final `invalid_output`, memes 2 articles qu'a la
  baseline Slice 8);
- aucun appel modele pour les 43 enrichissements deja reussis;
- aucune duplication d'audit pour un meme `run_id`;
- comptes reconcilies : Bronze/Silver/Enrichissement/Gold News a 45;
- schedule News actif (`0 0 0/6 * * ?`, `America/Toronto`, UNPAUSED);
- App `vigie-gold-viewer` RUNNING, compute ACTIVE;
- pipeline financier et Job financier inchanges.

## 7.2 Verification Databricks de la Slice 9 - 4 septembre 2026

Confirme :

- wheel `vigie_databricks_foundation-0.4.1-py3-none-any.whl` actif dans le
  Job News;
- run manuel `732901390317600` : `SUCCESS`;
- les 2 articles Survey Methodology auparavant `invalid_output` sont
  maintenant `succeeded` avec categories `["other"]`;
- audit : 45 entrees, `model_calls=2` <= budget 10, 45 succes, 0 erreur,
  0 sortie invalide et 0 differee;
- les 43 enrichissements deja reussis n'ont pas ete retraites;
- comptes Bronze/Silver/Enrichissement/Gold News reconcilies a 45;
- pipeline financier et Job financier inchanges.

## 8. Decisions structurantes

1. Tester, revoir, commiter et pousser chaque slice avant la suivante.
2. Utiliser Databricks Connect comme gate Spark/Delta.
3. Garder les objets durables dans `workspace.vigie`.
4. Nettoyer automatiquement les objets UUID de tests.
5. Garder l'App en lecture seule.
6. Separer les Jobs Finance et News.
7. Sauter les appels IA si contenu, prompt et modele sont inchanges.
8. Ne pas ajouter scoring, sentiment, RAG ou agent sans besoin valide.
9. Plafonner les appels modele par run et auditer chaque execution par `job.run_id`.

## 9. Risques et lecons

- L'idempotence d'etat ne garantit pas un no-op operationnel.
- L'isolation UUID sans cleanup peut saturer Unity Catalog.
- Un probe de connectivite ne doit pas devenir une dependance produit.
- Une erreur IA doit etre persistee sans corrompre Silver.
- Les droits d'utilisation des feeds live doivent etre valides avant adoption.
- Ne jamais reset/clean le repo sans verifier les changements utilisateur.
- Ne jamais conclure qu'un Job est sain a partir d'un ancien snapshot.

## 10. === RESUME HERE ===

### Etat

Slices 7, 8 et 9 terminees et verifiees. Tous les criteres d'acceptation de
la Slice 8 sont confirmes, dont le traitement progressif des lignes
differees. La Slice 9 a corrige les 2 `invalid_output` recurrents : le run
`732901390317600` a consomme 2 appels sur budget 10, a conserve les 43
succes existants et a enrichi les 2 lignes restantes avec `["other"]`.

### Action 1 - Surveiller les runs planifies

Le schedule 6 h est actif. Surveiller les prochaines lignes de
`workspace.vigie.news_ai_run_audit` : `model_calls <= 10`, compteurs
reconcilies, aucune source en echec.

### Action 2 - Prochaine portee

La feuille de route du produit cible est dans
`docs/INSURER_VIGIE_ROADMAP.md`. Les choix produit des Slices 10 a 14 sont
versionnes dans `config/finance_policy.yaml`. La prochaine action est le gate
Databricks du wheel 0.5.0 et du point d'entree `finance_publish` sur fixture :
tests Databricks Connect, run borne, rerun idempotent, audit
`workspace.vigie.finance_run_audit`, documents
`workspace.vigie.financial_documents`, reconciliation et verification du
last-known-good. Le Job reste sans schedule. L'acquisition live ne
sera activee qu'apres ce gate. Ne pas ajouter RAG, agent, sentiment ou scoring.

### Validation locale et Databricks Connect de la version 0.5.0

Confirme le 4 septembre 2026 :

- suite locale hors marqueurs Databricks reussie;
- wheel `vigie_databricks_foundation-0.5.0-py3-none-any.whl` construit;
- gate Databricks Connect complet reussi, sauf l'acceptation News live
  volontairement desactivee par `RUN_SLICE7_LIVE`;
- upserts Delta idempotents confirmes pour les documents et l'audit Finance;
- regression Spark Connect News corrigee par un schema Bronze explicite;
- tables de test UUID nettoyees;
- wheel, configuration et fixture televerses dans
  `/Users/jerome.plante@hotmail.com/vigie_databricks_finance`;
- Job Finance `319208446632488` migre vers `finance_publish` et wheel 0.5.0;
- premier run `647115018039226` SUCCESS : 4 insertions, comptes
  Bronze/Silver/Gold 7/7/6, aucune ligne rejetee, reconciliations a zero;
- rerun `429054234619694` SUCCESS : zero insertion, zero mise a jour, zero
  suppression et comptes inchanges 7/7/6;
- deux lignes `current` dans `workspace.vigie.finance_run_audit`, une par run;
- aucun schedule Finance actif.

Prochaine action : implementer et accepter la chaine d'acquisition live vers
`workspace.vigie.financial_documents` et le volume brut avant toute activation
du schedule. Conserver le mode fixture comme acceptance reproductible.

## 11. Instruction exacte de reprise

```text
Reprends vigie-industrie-databricks avec docs/PROJECT_HANDOFF.md.

Verifie d'abord Git. Les Slices 7, 8 et 9 sont terminees et verifiees ;
aucune nouvelle slice n'est cadree.

Les feeds Fabrication et Commerce international du Quotidien de Statistique
Canada sont approuves, deployes et planifies. Preserve le pipeline
financier, les Jobs independants, le cleanup Unity Catalog, l'idempotence
IA et le plafond d'appels modele.
```
