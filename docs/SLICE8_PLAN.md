# Slice 8 - Observabilite et maitrise des couts IA

## Objectif

Rendre chaque execution News auditable et imposer un plafond dur d'appels
modele sans perdre ni corrompre les articles en attente.

## Perimetre

- budget configurable `max_model_calls`, valeur initiale 10;
- selection deterministe par `article_id`;
- statut `budget_deferred` sans appel modele;
- table Delta `workspace.vigie.news_ai_run_audit`;
- une ligne idempotente par `job.run_id`;
- affichage read-only du dernier audit dans l'App;
- tests locaux et Databricks Connect sans appel modele reel.

## Hors perimetre

- alertes externes, courriel ou messagerie;
- cout monetaire estime sans donnees de facturation fiables;
- modification du pipeline financier;
- ajout de sources, RAG, agents, scoring ou sentiment.

## Contrat d'audit

`run_id`, `observed_at`, `input_rows`, `model_calls`, `max_model_calls`,
`succeeded_rows`, `failed_rows`, `invalid_output_rows`, `deferred_rows`,
`model_name`, `prompt_version`.

## Criteres d'acceptation

- budget zero produit zero appel et differe toutes les lignes non enrichies;
- un rerun traite progressivement les lignes differees;
- les enrichissements deja reussis ne consomment aucun budget;
- `model_calls <= max_model_calls` pour chaque audit;
- un retry du meme `run_id` met a jour au lieu de dupliquer;
- App saine si la table d'audit existe et message explicite sinon;
- Job financier et modules Bronze/Silver/Gold financiers inchanges;
- aucun secret et arbre Git propre apres push.

## Baseline observee avant deploiement

Runs planifies Slice 7 du 2026-09-04 :

- minuit : 39 nouvelles lignes, 39 appels modele, 38 succes, 5 sorties
  invalides et 2 echecs;
- 6 h : aucune insertion, 7 appels cibles, 43 succes et 2 sorties invalides;
- Bronze, Silver et Gold reconcilies a 45 lignes;
- deux sources disponibles et aucune source en echec.

Cette baseline confirme la valeur du plafond initial de 10 appels par run.
