# Vigie Industrie Databricks

@AGENTS.md

Les règles permanentes du dépôt (autorisations, contrats de tables, portes de
validation, routage des modèles) sont dans `AGENTS.md`, importé ci-dessus.
Ce fichier ajoute le contexte de travail propre à Claude Code.

## Contexte

Pipeline Databricks de vigie financière et d'actualités pour les assureurs
vie (MFC, SLF, GWO, IAG), avec un domaine P&C isolé (IFC, AV, TD, DFY) et une
App Streamlit en lecture seule (`apps/gold_viewer`). Voir `README.md`,
`docs/architecture.md` et
`docs/superpowers/specs/2026-09-29-current-state-baseline-design.md`.

## Structure

- `src/vigie_databricks/` : logique métier et traitement des données.
- `src/vigie_databricks/tasks/` : points d'entrée du wheel (`pyproject.toml`).
- `apps/gold_viewer/` : App Streamlit, lecture seule via SQL Warehouse.
- `config/` : contrat assurance, sources et politique Finance versionnés (YAML).
- `databricks*.json`, `databricks.yml` : Jobs et déploiement. Ne pas modifier
  les schedules ni les ressources live sans autorisation explicite.
- `scripts/` : outils manuels (staging, revue et publication P&C, etc.).
- `tests/` : suite pytest.

## Commandes

Python 3.12 requis.

```bash
python -m pip install -e ".[dev,local_spark]"
python -m pytest -m "not databricks_connect and not databricks_runtime" -q   # gate local (comme la CI)
python -m pytest -m databricks_connect -q -rs                                # gate Databricks Connect (accès workspace requis)
```

Les gates Databricks Connect, runtime et déploiement sont distincts du gate
local : signaler tout gate qui n'a pas pu être exécuté.

## Superpowers

Le plugin Superpowers est déclaré dans `.claude/settings.json`
(marketplace `obra/superpowers-marketplace`). À la première ouverture du
dépôt, accepter la confiance du dossier; le plugin s'installe alors
automatiquement. Sinon, manuellement :

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

Les specs et plans produits par ces skills vont dans `docs/superpowers/specs/`
et `docs/superpowers/plans/`.
