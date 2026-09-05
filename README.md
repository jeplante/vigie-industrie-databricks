# Vigie Industrie Databricks

Pipeline Databricks de vigie financière et d'actualités pour Manuvie (MFC),
Sun Life (SLF), Great-West Lifeco (GWO) et iA Groupe financier (IAG).

## État du projet

- Slices 0 à 9 : pipeline Bronze/Silver/Gold historique, Job News, enrichissement
  IA borné et App Streamlit en lecture seule, validés dans Databricks.
- Slices 10 à 14 : contrat assurance, acquisition bornée, extraction
  déterministe, publication last-known-good et secours IA. L'intégration locale
  du point d'entrée Finance est prête; son déploiement live reste volontairement
  en attente d'une acceptation Databricks.
- Slices 15 à 17 : actualités officielles des assureurs, expérience App et
  exploitation; non commencées.

Python 3.12 est la version supportée. Le package courant est `0.5.0`.

## Contrats durables

Tables existantes :

- `workspace.vigie.bronze_observations`
- `workspace.vigie.silver_observations`
- `workspace.vigie.gold_observations`
- `workspace.vigie.bronze_news`
- `workspace.vigie.silver_news`
- `workspace.vigie.news_ai_enrichment`
- `workspace.vigie.news_ai_run_audit`
- `workspace.vigie.gold_news`

Nouvel objet Finance à créer lors de l'acceptation :

- `workspace.vigie.financial_documents`
- `workspace.vigie.finance_run_audit`

Le point d'entrée `finance_publish` valide tout le lot avant la première
écriture. Un lot invalide écrit un audit `stale`, échoue le run et conserve les
tables Bronze/Silver/Gold existantes. Gold n'est avancé qu'après une
réconciliation Silver réussie.

Le point d'entrée `finance_live` découvre un seul rapport récent par assureur,
télécharge chaque document avec des limites strictes et des requêtes
conditionnelles ETag/Last-Modified, puis conserve le contenu par hash dans
`/Volumes/workspace/vigie/finance_raw`. L'extraction PDF est déterministe;
Model Serving n'est appelé que si elle ne produit aucun KPI. Un échec d'une
source bloque toute publication et toute activation du schedule.

Les périodes assurance utilisent `YYYY-Q1` à `YYYY-Q4` ou `YYYY-AN`. Silver et
Gold restent compatibles avec les anciens identifiants `YYYYQ1` à `YYYYQ4`.

## Politique Finance

La politique versionnée dans `config/finance_policy.yaml` fixe :

- rétention du contenu brut : 365 jours;
- volume cible : `/Volumes/workspace/vigie/finance_raw`;
- secours IA : Databricks Model Serving, maximum 10 appels par run;
- destination : App Databricks;
- réseau live désactivé par défaut.

Le navigateur et l'App ne contactent jamais les sources et ne déclenchent
aucune acquisition.

## Validation locale

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:UV_PROJECT_ENVIRONMENT='.test-venv'
$env:UV_PYTHON_INSTALL_DIR='.uv-python'
uv run --python 3.12 pytest -m "not databricks_connect and not databricks_runtime" -q
```

Gate Databricks Connect :

```powershell
uv run --extra databricks_connect --python 3.12 pytest -m databricks_connect -q -rs
```

## Déploiement Finance

`databricks_slice4_job.template.json` décrit le Job Finance live non planifié utilisant le
wheel `0.6.4`. Avant son premier run :

1. construire et téléverser le wheel;
2. téléverser `config/` et la fixture d'acceptation aux chemins configurés;
3. vérifier ou créer le volume Unity Catalog de contenu brut;
4. lancer les tests Databricks Connect;
5. exécuter un run fixture borné, puis un rerun identique;
6. vérifier l'audit, la réconciliation et les droits read-only de l'App;
7. garder le Job Finance sans schedule tant que l'acquisition live n'a pas passé
   son propre gate.

La feuille de route détaillée est dans `docs/INSURER_VIGIE_ROADMAP.md` et la
reprise opérationnelle dans `docs/PROJECT_HANDOFF.md`.
