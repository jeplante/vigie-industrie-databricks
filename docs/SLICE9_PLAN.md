# Slice 9 - Fiabilite des sorties IA invalides

## Etat

Diagnostiquee le 2026-09-04. Cause racine confirmee par reproduction.
Option A retenue le 2026-09-04 : conserver la taxonomie existante et
classifier les sujets sans categorie metier comme `"other"`. Implementation
locale terminee : prompt renforce et raisons de validation preservees dans
`error_code`. Tests unitaires et test Databricks Connect dedie reussis.
Wheel `0.4.1` deploye et Job News mis a jour. Verification live reussie sur
le run `732901390317600` : 2 appels modele, 45 succes, 0 sortie invalide,
0 ligne differee et tables News reconciliees a 45 lignes.

## Cause racine confirmee

Les 2 lignes `invalid_output` sont des entrees *Survey Methodology* de
Statistique Canada (titre long, description = "Catalogue number 12-001-X
(HTML | PDF)"). Reproduction en lecture seule (2 appels diagnostics hors
pipeline) : le modele retourne du JSON valide et complet
(`finish_reason=stop`), mais invente des categories hors vocabulaire :

- article 1 : `["research", "statistics"]`;
- article 2 : `["research", "methodology"]`.

Or `CATEGORIES` ([news_ai.py](src/vigie_databricks/news_ai.py)) ne contient
aucune de ces valeurs : `parse_output` rejette via la regle
`invalid_categories`. Ces sujets methodologiques ne correspondent a aucune
des 17 categories metier, donc le modele hallucine une etiquette au lieu
d'utiliser `"other"`. Constat secondaire : la table n'enregistre que
`invalid_model_output` (le loader fusionne les `ValueError` distincts), ce
qui masque la raison exacte sans reproduction manuelle.

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

Eliminer les echecs `invalid_categories` sur les sujets hors vocabulaire
et rendre la raison exacte d'un echec lisible sans reproduction manuelle,
sans changer le contrat JSON, sans toucher au pipeline financier et sans
depasser le plafond d'appels modele.

## Perimetre

- conserver la raison precise de validation (`invalid_categories`,
  `invalid_summary`, `invalid_output_schema`, `invalid_company_ids`,
  `empty_model_output`) dans `error_code` au lieu du generique
  `invalid_model_output`;
- renforcer le prompt (sans changer `prompt_version`) : indiquer
  explicitement d'utiliser `"other"` quand aucun libelle ne convient et de
  ne jamais inventer de categorie hors liste;
- les enrichissements reussis ne sont jamais retraites;
- tests locaux et Databricks Connect sans appel modele reel.

L'extrait de sortie brute est explicitement retire du perimetre : les
raisons precises dans `error_code` et le diagnostic ponctuel ont suffi pour
la cause racine observee. Il pourra etre reconsidere si une future erreur
ne peut pas etre expliquee par ces raisons.

## Hors perimetre

- scoring, sentiment, RAG, agents;
- ajout d'une categorie `research`/`methodology` au vocabulaire (decision
  metier, a valider separement);
- nouvelles sources ou nouvelle frequence;
- changement de modele ou de `prompt_version` (re-enrichirait tout
  l'historique et consommerait le budget de plusieurs runs);
- reparation par seconde tentative : inutile ici, l'echec est
  deterministe et corrige par le prompt;
- modification du pipeline financier;
- estimation de cout monetaire.

## Criteres d'acceptation

- cause racine documentee (extrait brut, regle `invalid_categories`);
- les 2 articles sont enrichis avec succes apres renforcement du prompt,
  ou marques irreparables avec cause precise;
- la raison exacte d'un echec est lisible dans `error_code`;
- `model_calls <= max_model_calls` pour chaque audit;
- budget zero reste zero appel;
- aucun retraitement des enrichissements reussis;
- Job financier et modules financiers inchanges;
- aucun secret et arbre Git propre apres push.

## Resultat de validation - 2026-09-04

- 6 tests cibles reussis (unitaires, contrat et Databricks Connect);
- le test Databricks Connect confirme que `invalid_categories` est persiste
  dans `error_code`;
- le run live `732901390317600` est `SUCCESS` et utilise le wheel `0.4.1`;
- les 2 articles Survey Methodology sont `succeeded`, categories
  `["other"]`, `error_code` nul;
- audit live : `model_calls=2` <= `max_model_calls=10`, 45 succes,
  0 echec, 0 sortie invalide et 0 differee;
- Bronze/Silver/Enrichissement/Gold News : 45 lignes chacun.
