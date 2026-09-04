# PROJECT HANDOFF - vigie-industrie-databricks

**Mise a jour : 2026-09-03 (America/Toronto)**
**Repo :** `C:\Users\jerom\vigie_databricks`
**GitHub :** `jeplante/vigie-industrie-databricks`
**Branche / HEAD :** `main` / `1135f734607469b708100828a93b39aa0ebb0e28`

> **ETAT VERIFIE.** Slice 6 est commitee et poussee. Le depot est propre et `main` est synchronisee avec `origin/main`. Le gate Databricks en lecture seule a ete complete le 3 septembre 2026.

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
| 7 - News live | Cadree, non implementee | voir `docs/SLICE7_PLAN.md` |

Le commit Slice 6 porte le message peu descriptif `update`, mais contient exactement les 20 chemins attendus : 586 insertions et 4 suppressions. Ne pas reecrire l'historique uniquement pour renommer ce commit.

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
  -> workspace.vigie.news_ai_enrichment
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
- `workspace.vigie.gold_news`.

Comptes confirmes le 3 septembre : Finance 3/3/2; News 2/2/2/2.

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
- aucun schedule dans le template actuel.

### App

- nom : `vigie-gold-viewer`;
- URL connue : `https://vigie-gold-viewer-7474651721951651.aws.databricksapps.com`;
- resource binding : `sql_warehouse`;
- configuration versionnee : `workspace.vigie.gold_observations` et `workspace.vigie.gold_news`;
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

## 8. Decisions structurantes

1. Tester, revoir, commiter et pousser chaque slice avant la suivante.
2. Utiliser Databricks Connect comme gate Spark/Delta.
3. Garder les objets durables dans `workspace.vigie`.
4. Nettoyer automatiquement les objets UUID de tests.
5. Garder l'App en lecture seule.
6. Separer les Jobs Finance et News.
7. Sauter les appels IA si contenu, prompt et modele sont inchanges.
8. Ne pas ajouter scoring, sentiment, RAG ou agent sans besoin valide.

## 9. Risques et lecons

- L'idempotence d'etat ne garantit pas un no-op operationnel.
- L'isolation UUID sans cleanup peut saturer Unity Catalog.
- Un probe de connectivite ne doit pas devenir une dependance produit.
- Une erreur IA doit etre persistee sans corrompre Silver.
- Les droits d'utilisation des feeds live doivent etre valides avant adoption.
- Ne jamais reset/clean le repo sans verifier les changements utilisateur.
- Ne jamais conclure qu'un Job est sain a partir d'un ancien snapshot.

## 10. === RESUME HERE ===

### Action 1 - Decision sur les sources Slice 7

Recommandation :

1. Statistique Canada - Le Quotidien - Fabrication;
2. Statistique Canada - Le Quotidien - Commerce international.

Voir `docs/SLICE7_PLAN.md` pour les URLs, conditions et garde-fous.

### Action 2 - Slice 7

Utiliser `docs/SLICE7_PLAN.md`. La Slice vise une acquisition News live configurable et planifiee tout en conservant fixture, idempotence, isolation et limites de cout.

Ne pas commencer la persistance live avant approbation des sources et de leurs conditions d'usage. Ne pas ajouter RAG, agent, sentiment ou scoring.

## 11. Instruction exacte de reprise

```text
Reprends vigie-industrie-databricks avec docs/PROJECT_HANDOFF.md.

Verifie d'abord Git et utilise docs/SLICE7_PLAN.md.

Les sources recommandees sont les feeds Fabrication et Commerce international
du Quotidien de Statistique Canada. Obtiens leur approbation explicite avant
toute persistance live. Preserve le pipeline financier, les Jobs independants,
le cleanup Unity Catalog et l'idempotence IA.
```
