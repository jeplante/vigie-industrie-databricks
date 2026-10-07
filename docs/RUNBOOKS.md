# Runbooks d'exploitation - Vigie assurance (Databricks)

**Etat observe le 2026-10-07.** Les valeurs (identifiants de Jobs, versions de wheel) changent: relire
l'etat reel avec `databricks jobs get <id>` avant d'agir, et mettre ce document a jour apres un changement.
**Statut des procedures.** Eprouvees en conditions reelles le 2026-10-07: relance avec et sans `dry_run` (4), migration vers un
nouveau wheel (6, sens aller), sauvegarde/deploiement/verification de l'App (7, sens aller), droits de lecture (8), lecture de la
consommation (9). **Jamais executees**: la pause d'un schedule (3), `RESTORE` d'une table (5), le sens retour des sections 6 et 7
(les fichiers de retour arriere existent mais n'ont pas ete appliques), et l'exercice de panne (10) tant que cette ligne n'est
pas remplacee par son resultat. Les executer une premiere fois sur un element sans enjeu avant d'en avoir besoin.

## 0. Avant toute commande

- Workspace Databricks **Free Edition** (apprentissage): aucune facture, mais un quota de calcul non publie.
  Un depassement arrete le calcul le reste de la journee. Les Apps s'arretent automatiquement apres 24 h, et
  5 taches de Job au plus tournent en meme temps. Voir la section 9.
- Profil CLI: `jeplante` (authentification `databricks-cli`). Verifier: `databricks auth profiles` (colonne Valid).
- **Lancer le CLI depuis un dossier hors du depot** (par exemple `C:\Users\jerom`). Le `databricks.yml` du depot est un
  gabarit de bundle vide avec un hote factice (`https://<your-workspace-host>`): depuis le depot, le CLI le lit et
  refuse le profil (`the host in the profile ... doesn't match the host configured in the bundle`).
- Sous Git Bash, prefixer `MSYS_NO_PATHCONV=1` pour que les chemins `/Workspace/...` ne soient pas reecrits.
- Un `--json @fichier.json` demande l'identifiant du Job **dans** le JSON (`{"job_id": ..., "new_settings": {...}}`).
- Avant de modifier un Job: sauvegarder sa configuration (`databricks jobs get <id> --output json > avant.json`) et
  preparer le fichier de retour arriere en meme temps que le fichier de changement.

## 1. Jobs et cadences

| Job | Id | Cadence (America/Toronto) | Contenu |
|---|---|---|---|
| vigie-finance-live | 319208446632488 | 06:15 quotidien | acquisition et publication Finance vie |
| vigie-pnc-news | 199998716914987 | 06:20 quotidien | salles de presse officielles des 4 assureurs P&C |
| vigie-app-start | 494550201015118 | 06:30 quotidien | demarre l'App si elle est arretee |
| vigie-operations-monitor | 737745708117826 | 06:45 quotidien | alertes (App, Finance, trimestre, consommation) |
| vigie-official-investor-news | 1118291153119927 | toutes les 6 h | actualites officielles vie et media sectoriel |
| vigie-pnc-acquisition-review | 313136866676385 | manuel | acquisition des documents P&C vers le staging |
| vigie-finance-history-publish | 623558766235360 | manuel | reprise historique Finance (ponctuelle) |

Les Jobs planifies envoient un courriel a l'echec. Le monitor **echoue volontairement** s'il detecte une alerte: son
courriel est le canal d'alerte.

## 2. Verification quotidienne (5 minutes)

1. Courriel d'echec recu? Si non, passer a 2.
2. `databricks jobs list-runs --job-id <id> --limit 3` pour les 5 Jobs planifies: `SUCCESS`, a l'heure attendue.
3. Monitor: lire la derniere sortie (`databricks jobs get-run-output <task_run_id>`): `alerts` doit etre vide.
4. App: la barre laterale affiche partout `OK` (ou `N/A` pour la lacune Aviva), aucune alerte d'exploitation.
5. Consommation: l'alerte `usage_spike` (seuil empirique de 30 DBU/jour) est le voyant; le detail est lisible dans
   `system.billing.usage`.

## 3. Mettre en pause et reprendre un schedule

```powershell
# pause (remplacer l'identifiant et reprendre les valeurs de cron/fuseau du Job)
databricks jobs get <id> --output json            # noter quartz_cron_expression et timezone_id
# fichier pause.json: {"job_id": <id>, "new_settings": {"schedule": {"quartz_cron_expression": "<cron>", "timezone_id": "America/Toronto", "pause_status": "PAUSED"}}}
databricks jobs update --json "@pause.json"
```
Reprendre = meme fichier avec `"UNPAUSED"`. Le `schedule` est remplace en bloc: toujours reprendre le cron existant.

## 4. Relancer une source ou un Job

- Essai sans ecriture: `databricks jobs run-now --json '{"job_id": <id>, "job_parameters": {"dry_run": "true"}}'`.
- Persistant: meme commande avec `"dry_run": "false"`. Les ecritures sont idempotentes (MERGE sur l'identifiant d'article
  ou d'observation): un second run identique doit afficher 0 insertion et 0 mise a jour.
- Actualites vie: la tache `official_news` ne publie un lot que si les 4 sources repondent (le dernier lot valide est
  preserve). Une source en echec est **nommee** dans `official_news_audit.per_source_json` et dans la barre laterale.
- Actualites P&C: chaque source est independante; les succes sont publies et l'echec est nomme dans
  `pnc_news_audit.per_source_json` (le Job echoue apres l'ecriture pour declencher le courriel).

## 5. Restaurer le dernier etat valide d'une table (Delta)

Les tables Delta gardent leur historique (voyage dans le temps). Procedure type, sur l'entrepot SQL:

```sql
DESCRIBE HISTORY workspace.vigie.<table>;                       -- reperer la version d'avant l'incident
SELECT count(*) FROM workspace.vigie.<table> VERSION AS OF <n>; -- verifier le contenu
RESTORE TABLE workspace.vigie.<table> TO VERSION AS OF <n>;
```
- Finance publiee: `bronze_observations`, `silver_observations`, `gold_observations` sont publiees ensemble par le Job.
  **La publication n'est pas atomique entre tables**: apres une restauration, restaurer les trois a la meme epoque
  puis verifier les comptes (`reconciliation` du Job). Ne jamais presenter cette publication comme atomique.
- P&C publie: `pnc_gold_observations`. Une republication revue passe par `scripts/publish_pnc_reviewed.py`
  (voir `docs/PNC_SOURCE_REVIEW.md`): d'abord sans `--publish`, puis avec, puis relecture independante.
- Journaux et audits (`*_audit`, `pnc_candidates`): ne pas restaurer pour corriger l'App; ce sont des historiques.

## 6. Retour arriere d'un wheel ou de la configuration d'un Job

Les wheels sont **versionnes et jamais ecrases** dans `/Users/jerome.plante@hotmail.com/vigie_databricks_finance/`
(Finance, actualites vie, monitor) et `/Users/jerome.plante@hotmail.com/vigie_pnc/<version>/` (Jobs P&C, avec leur config).
Revenir en arriere = repointer le Job sur l'ancien wheel:

```powershell
databricks jobs get <id> --output json > avant.json        # avant le changement
# retour: reappliquer le fichier de retour arriere prepare (environments avec l'ancien wheel)
databricks jobs update --json "@retour.json"
```
Toujours valider un nouveau wheel par un run `dry_run=true` avant le prochain run planifie, et verifier que le contenu du
wheel est identique aux sources (comparer `vigie_databricks/<module>.py` du wheel aux fichiers du depot).

## 7. Retour arriere de l'App

Source deployee: `/Workspace/Users/jerome.plante@hotmail.com/vigie_gold_viewer`.

```powershell
$p = "/Workspace/Users/jerome.plante@hotmail.com/vigie_gold_viewer"
databricks workspace export-dir $p "C:\sauvegarde\app_avant"             # sauvegarde AVANT de deployer
# copier apps/gold_viewer sans __pycache__, puis:
databricks workspace import-dir "<copie propre>" $p --overwrite
databricks apps deploy vigie-gold-viewer --source-code-path $p
# retour: import-dir depuis la sauvegarde, puis un nouveau apps deploy
```
Verifier ensuite: deploiement `SUCCEEDED`, `databricks apps get vigie-gold-viewer` = `RUNNING` / `ACTIVE`, et la source
deployee identique a `apps/gold_viewer` (`export-dir` puis comparaison fichier par fichier).

## 8. Droits de lecture de l'App (lecture seule)

Le service principal de l'App (client id dans `scripts/grant_pnc_app_read.json`) ne recoit que `SELECT`. Accorder:
`databricks grants update table workspace.vigie.<table> --json "@scripts/grant_pnc_app_read.json"`.
Tables P&C lisibles: `pnc_gold_observations`, `pnc_run_audit`, `pnc_financial_documents`, `pnc_official_news`,
`pnc_news_audit`. Verifier: `SELECT grantee, privilege_type FROM workspace.information_schema.table_privileges WHERE table_name = '<table>'`.
L'isolation P&C est une regle du depot: ne pas accorder de droit croise vie/P&C et ne pas melanger les tables.

**Secrets.** Il n'y a aucun secret externe a faire tourner: l'authentification est le profil OAuth du CLI
(`databricks auth login --profile jeplante` pour renouveler) et l'identite de l'App est geree par la plateforme.
Aucun appel a un fournisseur de modele externe; les appels de modele Databricks sont plafonnes dans le code.

## 9. Free Edition: limites et symptomes

- Quota de calcul non publie: un Job qui echoue pour cause de ressources signale un quota atteint. Verifier
  `system.billing.usage` (DBU par jour et par produit). Observe: environ 1,2 DBU/jour pour les Jobs seuls, l'App ajoute
  0,5 DBU/h quand elle tourne (jusqu'a 12/jour), l'entrepot SQL s'ajoute a l'usage; des journees a 17-19 DBU ont eu lieu
  sans arret observe.
- L'App s'arrete apres 24 h: `vigie-app-start` la redemarre a 06:30 (le monitor la controle a 06:45).
- Si le quota est un probleme: limiter `vigie-app-start` aux jours ouvrables (le monitor alertera alors l'App arretee la fin
  de semaine: ajuster en consequence), ou ne demarrer l'App qu'a la demande.

## 10. Exercice de panne (sans toucher la production)

La tache `official_news` accepte `--target` et `--audit-table` (par defaut les tables de production) pour pouvoir simuler
une panne dans un schema jetable:

1. `CREATE SCHEMA workspace.vigie_drill;`
2. Lancer un run unique (`databricks jobs submit`) de la tache avec `--config-directory` pointant vers un dossier vide (la
   source Manulife echoue), `--dry-run false`, `--target workspace.vigie_drill.official_news`,
   `--audit-table workspace.vigie_drill.official_news_audit`.
3. Attendu: run `FAILED` (`Official News source gate failed`), aucune ligne dans `official_news`, une ligne d'audit avec
   `MFC` en `failed` et les trois autres sources en `ok`.
4. `DROP SCHEMA workspace.vigie_drill CASCADE;` (verifier d'abord que le schema ne contient que ces deux tables).
