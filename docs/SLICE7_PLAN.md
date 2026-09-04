# SLICE 7 PLAN - Acquisition News live et planification controlee

**Statut :** cadrage pret pour validation et implementation
**Date :** 2026-09-03
**Prerequis :** gate de sante Databricks en lecture seule apres renouvellement OAuth

## 1. Objectif

Faire passer le pipeline News de la fixture d'acceptation a une acquisition live configurable et planifiee, sans ajouter RAG, agent, sentiment ou scoring.

L'App doit afficher automatiquement des nouvelles recentes de sources approuvees, enrichies une seule fois par combinaison contenu/prompt/modele, avec provenance et fallback global explicite.

## 2. Perimetre inclus

1. Selectionner une ou deux sources RSS publiques et stables.
2. Documenter proprietaire, URL, portee, frequence et conditions d'usage.
3. Ajouter une configuration multi-source minimale et validee.
4. Conserver `tests/fixtures/slice6_news_rss.xml` comme gate deterministe.
5. Preserver identite, deduplication et idempotence IA.
6. Ajouter timeout, limite de taille et limite d'articles par source/run.
7. Isoler l'echec d'une source.
8. Ajouter une planification Databricks prudente.
9. Exposer articles lus/inseres/mis a jour/rejetes/enrichis/sautes/echoues et appels modele.
10. Tester la reprise apres erreur source et erreur modele.
11. Verifier l'App en lecture seule et le pipeline financier inchange.
12. Mettre a jour README, template Job et handoff.

## 3. Hors perimetre

- RAG, vector store, agent ou chatbot;
- sentiment, importance, score ou recommandation;
- scraping HTML generaliste;
- source payante ou avec secret sans decision explicite;
- refonte de l'App;
- modification du pipeline financier;
- nombreuses sources dans la meme slice;
- suppression d'objets Unity Catalog.

## 4. Decisions proposees

### Sources

Commencer avec au maximum deux feeds officiels. Le feed BBC du probe Slice 6 n'est pas automatiquement approuve comme dependance produit.

Criteres :

- RSS/Atom officiel;
- HTTPS et URL stable;
- metadonnees suffisantes;
- pertinence pour la vigie industrielle;
- aucune authentification pour cette slice;
- conditions compatibles avec stockage des metadonnees, resume genere et lien source.

Sources recommandees apres verification du 3 septembre 2026 :

1. `statcan_manufacturing`
   - produit : Statistique Canada, Le Quotidien, Fabrication;
   - URL : `https://www150.statcan.gc.ca/n1/rss/dai-quo/16-eng.atom`;
   - portee : publications officielles sur la fabrication;
   - historique du feed : dernier 100 jours selon la page officielle.
2. `statcan_international_trade`
   - produit : Statistique Canada, Le Quotidien, Commerce international;
   - URL : `https://www150.statcan.gc.ca/n1/rss/dai-quo/12-eng.atom`;
   - portee : publications officielles sur le commerce international;
   - historique du feed : dernier 100 jours selon la page officielle.

Justification :

- feeds Atom officiels explicitement fournis pour abonnement;
- pertinence directe pour une vigie industrielle canadienne;
- metadonnees publiques et source primaire;
- licence ouverte de Statistique Canada permettant utilisation et produits a
  valeur ajoutee sous reserve d'exactitude, absence d'endossement et attribution.

Attribution a implementer dans l'App ou la fiche source :

`Adapte de Statistique Canada, Le Quotidien, [sujet], [date de reference]. Ceci ne constitue pas un endossement de Statistique Canada.`

Ne pas utiliser les logos ou symboles officiels. Conserver le lien vers l'article
source. Revalider la licence au moment du deploiement, puisqu'elle peut etre modifiee.

Probe HTTP sans persistance du 3 septembre 2026 :

| Source | HTTP | Type | Taille | Entrees | Derniere mise a jour du feed |
|---|---:|---|---:|---:|---|
| `statcan_manufacturing` | 200 | `application/atom+xml` | 17 231 octets | 24 | 2026-08-27 08:30 -04:00 |
| `statcan_international_trade` | 200 | `application/atom+xml` | 13 944 octets | 20 | 2026-08-04 08:30 -04:00 |

Les deux feeds sont accessibles et conformes a Atom. Aucune donnee n'a ete
ecrite dans Databricks pendant ce probe.

### Configuration

Utiliser un petit fichier versionne ou parametre JSON valide contenant `source_id`, `url`, `enabled` et optionnellement `category`. Aucune URL arbitraire ne vient de l'UI.

### Planification

Proposition initiale : toutes les 6 heures, fuseau `America/Toronto`, `max_concurrent_runs=1`. Confirmer la frequence apres observation du volume et du cout.

### Cout

- limiter articles par source et par run;
- enrichir uniquement les contenus nouveaux;
- borner la sortie du modele;
- ne pas reessayer indefiniment une erreur permanente;
- rapporter appels et tokens.

## 5. Architecture minimale

```text
Sources approuvees
  -> acquisition RSS live bornee
  -> workspace.vigie.bronze_news
  -> workspace.vigie.silver_news
  -> skip si contenu/prompt/modele inchanges
  -> workspace.vigie.news_ai_enrichment
  -> workspace.vigie.gold_news
  -> App read-only
```

Le Job News reste independant du Job financier.

## 6. Garde-fous

### Acquisition

- timeout explicite;
- taille maximale de reponse;
- type de contenu attendu;
- parseur RSS/Atom defensif;
- limite d'articles;
- erreur d'une source isolee;
- journaux sans secrets.

### Idempotence

`content_hash` exclut `fetched_at`. Un rerun identique produit zero nouvel article, zero mise a jour materielle et zero appel modele.

### IA

Conserver modele configurable, defaut `databricks-gpt-oss-20b`, temperature zero, sortie bornee, JSON valide, `prompt_version`, usage et statut d'echec sans blocage de Silver.

### Protection Finance

Aucun changement dans :

- `src/vigie_databricks/bronze.py`;
- `src/vigie_databricks/silver.py`;
- `src/vigie_databricks/gold.py`;
- Job financier `319208446632488`.

## 7. Phases

### A - Gate et decouverte

1. Gate Databricks complete le 3 septembre 2026.
2. Documentation et conditions des deux feeds Statistique Canada verifiees.
3. Lire un petit echantillon des deux feeds sans persistance.
4. Faire approuver sources, attribution et frequence.

Critere : aucune ecriture Databricks; sources/cadence approuvees.

### B - Configuration et acquisition

1. Ajouter configuration multi-source.
2. Implementer validation, timeout, taille et limites.
3. Preserver le mode fixture.
4. Tester succes, feed invalide, timeout simule, article incomplet et doublon.

Critere : tests locaux verts; fixture intacte.

### C - Integration Databricks

1. Executer Connect avec objets UUID.
2. Confirmer cleanup.
3. Faire un seul run live borne.
4. Faire une acceptance IA controlee.
5. Rerun identique et prouver `model_calls=0`.

Critere : reconciliation, aucun doublon, cleanup vert, etat durable valide.

### D - Planification et App

1. Ajouter le schedule au template apres validation.
2. Deployer la configuration.
3. Verifier l'App read-only.
4. Confirmer que le Job financier n'a pas ete declenche.
5. Documenter rollback : desactiver le schedule sans supprimer les tables.

Critere : planification active, run planifie observe avec succes, App saine.

### E - Closeout

1. Tests locaux.
2. Suite Connect.
3. Diff cible et recherche de secrets.
4. `git diff --cached --check`.
5. Commit descriptif et push.
6. Mettre a jour le handoff.

## 8. Criteres d'acceptation

- au moins une source live approuvee;
- acquisition bornee et configurable;
- fixture deterministe verte;
- aucune duplication Bronze/Silver/AI/Gold;
- rerun identique avec `model_calls=0`;
- erreur source sans corruption;
- erreur modele sans invalider Silver;
- schedule documente et desactivable;
- App saine et read-only;
- pipeline financier inchange;
- aucun secret;
- tests locaux et Connect verts;
- arbre Git propre apres push.

## 9. Decisions humaines requises avant persistance live

- sources RSS;
- frequence;
- maximum d'articles par source/run;
- retention de `raw_payload`;
- comportement si toutes les sources echouent;
- budget quotidien d'appels modele.

## 10. Instruction d'execution

```text
Implement Slice 7 only from docs/SLICE7_PLAN.md.

First complete the read-only Databricks health gate. Do not run any Job or model
during discovery. Present candidate sources and their terms for human approval
before persisting live data.

Preserve fixture mode, financial modules, independent Jobs, Unity Catalog
cleanup and AI idempotence. Do not add RAG, agents, sentiment, scoring or UI
redesign.
```

## 11. Etat de realisation - 2026-09-03

Slice 7 est implementee et acceptee :

- deux feeds Atom de Statistique Canada approuves et configures;
- acquisition bornee a 25 articles par source et par run;
- horaire actif toutes les 6 heures, fuseau `America/Toronto`;
- wheel deploye : `vigie_databricks_foundation-0.3.1-py3-none-any.whl`;
- Job News : `1118291153119927`;
- run live borne : 2 sources, 4 articles, aucune source en echec;
- contrat IA `slice7-news-enrichment-v2`, 6 enrichissements reussis;
- rerun identique : aucune insertion/mise a jour et `model_calls=0`;
- App `vigie-gold-viewer` deployee et RUNNING avec attribution;
- modules financiers inchanges.
