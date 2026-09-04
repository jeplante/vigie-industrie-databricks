# Slice 9 - Fiabilite des sorties IA invalides

## Etat

Proposee le 2026-09-04, en attente de validation. Aucune implementation
demarree.

## Besoin valide

Les audits des Slices 7 et 8 montrent un echec reproductible :

- baseline Slice 8 (2026-09-04) : run de minuit, 5 sorties invalides;
  run de 6 h, 2 sorties invalides;
- run manuel `937246177868747` (2026-09-04) : les 2 lignes differees de
  l'acceptation budget zero sont retombees en `invalid_output`;
- ce sont les 2 memes articles a chaque run.

Ces lignes non reussies sont retirees a chaque execution et consomment du
budget (`model_calls`) sans produire d'enrichissement. Conformement a la
decision structurante 8, cette slice ne propose ni scoring, ni sentiment,
ni RAG, ni agent : elle durcit le contrat existant.

## Objectif

Diagnostiquer les sorties invalides et reduire leur taux sans changer le
contrat JSON, sans toucher au pipeline financier et sans depasser le
plafond d'appels modele.

## Perimetre

- journaliser un extrait borne de la sortie brute en cas d'echec de
  validation (ex. 500 caracteres, jamais l'article complet);
- une reparation bornee : au plus une seconde tentative par article avec
  instruction de reparation JSON, comptee dans le meme budget
  `max_model_calls`;
- la reparation est une etape technique du meme appel logique : elle ne
  change ni `prompt_version` ni l'identite d'enrichissement;
- les enrichissements reussis ne sont jamais retraites;
- si necessaire, extension additive du contrat d'audit (`repaired_rows`)
  via `ALTER TABLE`, documentee;
- tests locaux et Databricks Connect sans appel modele reel.

## Hors perimetre

- scoring, sentiment, RAG, agents;
- nouvelles sources ou nouvelle frequence;
- changement de modele ou de `prompt_version` (re-enrichirait tout
  l'historique et consommerait le budget de plusieurs runs);
- modification du pipeline financier;
- estimation de cout monetaire.

## Criteres d'acceptation

- cause racine des 2 sorties invalides actuelles documentee (extrait
  brut, raison de validation);
- les 2 articles sont repares ou marques irreparables avec cause;
- `model_calls <= max_model_calls` pour chaque audit, reparation incluse;
- budget zero reste zero appel;
- aucun retraitement des enrichissements reussis;
- Job financier et modules financiers inchanges;
- aucun secret et arbre Git propre apres push.
