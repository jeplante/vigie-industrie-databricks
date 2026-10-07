# Runbooks d'exploitation - Vigie assurance (Databricks)

**Etat observe le 2026-10-07.** Les valeurs (identifiants de Jobs, versions de wheel) changent: relire
l'etat reel avec `databricks jobs get <id>` avant d'agir, et mettre ce document a jour apres un changement.
**Statut des procedures** (2026-10-07). Eprouvees en conditions reelles: relance avec et sans `dry_run` (4), pause et reprise d'un
schedule (3), `RESTORE` d'une table Delta (5), migration et retour arriere de la configuration d'un Job (6, sur un Job jetable
supprime ensuite), sauvegarde/deploiement/verification de l'App (7, sens aller), droits de lecture (8), lecture de la consommation (9),
exercice de panne (10). **Jamais executee**: le retour arriere de l'App (7, sens retour): redeployer volontairement une ancienne
version en production a ete refuse par le garde-fou de la session; a executer une premiere fois par le user ou avec une autorisation
explicite, de preference un moment calme.

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
| vigie-pnc-news | 199998716914987 | 06:20 quotidien | salles de presse des 4 assureurs P&C et medias sectoriels |
| vigie-app-start | 494550201015118 | 06:30 quotidien | demarre l'App si elle est arretee |
| vigie-operations-monitor | 737745708117826 | 06:45 quotidien | alertes (App, Finance, trimestre vie et P&C, consommation) |
| vigie-official-investor-news | 1118291153119927 | toutes les 6 h | actualites officielles vie et media sectoriel |
| vigie-pnc-acquisition-review | 313136866676385 | manuel | acquisition des documents P&C vers le staging |
| vigie-finance-history-publish | 623558766235360 | manuel | reprise historique Finance (ponctuelle) |

Les Jobs planifies envoient un courriel a l'echec. Le monitor **echoue volontairement** s'il detecte une alerte: son
courriel est le canal d'alerte.

**Regle de publication des actualites (vie et P&C, depuis 0.10.15).** Les sources qui repondent sont publiees; une source
en echec garde ses derniers articles (le `MERGE` ne supprime jamais), l'audit la nomme et le run echoue pour que le Job
alerte. Medias sectoriels: moins de 2 fils lus fait echouer le run, dans les deux univers.

**Alertes P&C du monitor (depuis 0.10.15).** Les KPI P&C sont publies apres une revue humaine des preuves, donc:
- `pnc_quarter_incomplete` (avertissement): un KPI attendu manque pour le dernier trimestre clos depuis 50 jours, selon le
  calendrier de l'assureur (exercice fiscal de TD: novembre a octobre). Aviva Canada n'est jamais attendu. Action: faire la
  revue P&C et publier.
- `pnc_results_announced` (avertissement): un communique officiel annonce des resultats trimestriels plus recents que la
  derniere publication de cet assureur. Action: meme revue, souvent avant que l'alerte precedente ne se declenche.
- `pnc_value_anomalous` (critique): un ratio publie sort de sa plage plausible, ou sinistres + frais ne donnent pas le
  ratio combine (tolerance 0,5 pp). Action: verifier la preuve, corriger par une nouvelle publication revue.
- `pnc_unreadable` (avertissement): le monitor n'a pas pu lire les tables P&C.

## 2. Verification quotidienne (5 minutes)

1. Courriel d'echec recu? Si non, passer a 2.
2. `databricks jobs list-runs --job-id <id> --limit 3` pour les 5 Jobs planifies: `SUCCESS`, a l'heure attendue.
3. Monitor: lire la derniere sortie (`databricks jobs get-run-output <task_run_id>`): `alerts` doit etre vide.
4. App: la barre laterale affiche partout `OK` (ou `N/A` pour la lacune Aviva), aucune alerte d'exploitation.
5. Consommation: l'alerte `usage_spike` (seuil empirique de 30 DBU/jour) est le voyant; le detail est lisible dans
   `system.billing.usage`.

## 3. Mettre en pause et reprendre un schedule

*Exercice reel du 2026-10-07 sur `vigie-pnc-news`: pause puis reprise en quelques secondes, etat final identique (cron, fuseau, parametres, courriel, wheel).*

```powershell
# pause (remplacer l'identifiant et reprendre les valeurs de cron/fuseau du Job)
databricks jobs get <id> --output json            # noter quartz_cron_expression et timezone_id
# fichier pause.json: {"job_id": <id>, "new_settings": {"schedule": {"quartz_cron_expression": "<cron>", "timezone_id": "America/Toronto", "pause_status": "PAUSED"}}}
databricks jobs update --json "@pause.json"
```
Reprendre = meme fichier avec `"UNPAUSED"`. Le `schedule` est remplace en bloc: toujours reprendre le cron existant.

## 4. Relancer une source ou un Job

- Essai sans ecriture: `databricks jobs run-now --json '{"job_id": <id>, "job_parameters": {"dry_run": "true"}}'`.
- Une tache en echec est **reessayee une fois par la plateforme** (observe: tentatives 0 et 1): une panne persistante ecrit donc
  deux lignes d'audit par run. L'App lit la plus recente, c'est sans consequence.
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

**Exercice reel (2026-10-07, table jetable de 3 puis 5 lignes).** `DESCRIBE HISTORY` donne `0 CREATE TABLE`, `1 WRITE` (3 lignes saines),
`2 WRITE` (l'incident: 2 lignes ajoutees). Piege vecu: restaurer a la version 2 est sans effet, c'est l'etat de l'incident; la bonne
version est celle d'**avant** l'incident (1). Le controle `SELECT count(*) ... VERSION AS OF <n>` l'avait montre (5 lignes au lieu de 3):
ne jamais sauter ce controle. `RESTORE TABLE ... TO VERSION AS OF 1` a rendu les 3 lignes saines et a cree lui-meme une nouvelle
version (3, `RESTORE`): l'historique est conserve, l'operation est donc elle-meme annulable.

## 6. Retour arriere d'un wheel ou de la configuration d'un Job

Les wheels sont **versionnes et jamais ecrases** dans `/Users/jerome.plante@hotmail.com/vigie_databricks_finance/`
(Finance, actualites vie, monitor) et `/Users/jerome.plante@hotmail.com/vigie_pnc/<version>/` (Jobs P&C, avec leur config).
Revenir en arriere = repointer le Job sur l'ancien wheel:

```powershell
databricks jobs get <id> --output json > avant.json        # avant le changement
# retour: reappliquer le fichier de retour arriere prepare (environments avec l'ancien wheel)
databricks jobs update --json "@retour.json"
```
**Exercice reel**: un Job jetable (jamais execute) a ete cree sur le wheel 0.10.13, migre vers 0.10.14 puis ramene a 0.10.13 avec le
fichier de retour arriere; seul `environments` change, parametres, schedule et courriel restent identiques. Le Job a ete supprime.

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
`pnc_news_audit`, `pnc_editorial_news`. **Toute nouvelle table lue par l'App doit recevoir ce droit au moment de sa
creation**: le droit est donne table par table, pas sur le schema (oubli vecu le 2026-10-07 avec `pnc_editorial_news`). Verifier: `SELECT grantee, privilege_type FROM workspace.information_schema.table_privileges WHERE table_name = '<table>'`.
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
3. Attendu depuis 0.10.15: run `FAILED` (`Official News sources failed: MFC; their last-known articles are kept`), les
   articles des trois autres sources publies dans `official_news` du schema jetable, une ligne d'audit avec
   `sources_succeeded = 3`, `MFC` en `failed` et les trois autres sources en `ok`. (Avant 0.10.15: rien n'etait publie.)
4. `DROP SCHEMA workspace.vigie_drill CASCADE;` (verifier d'abord que le schema ne contient que ces deux tables).

**Resultat observe le 2026-10-07** (wheel 0.10.14, ancienne regle, run unique `vigie-failure-drill`): le run a fini en `FAILED` avec
`Official News source gate failed; last-known-good preserved`; la table `official_news` du schema jetable n'a pas ete creee
(rien n'a ete publie); l'audit contenait `MFC` en `failed` avec sa cause (`Cannot read contract file ...`) et `SLF`, `GWO`,
`IAG` en `ok` (3, 2 et 3 articles lus), en **deux lignes** (une par tentative). Le schema a ete supprime ensuite.
Note: `databricks jobs submit --timeout` n'affiche pas de JSON quand le run echoue; retrouver le run avec
`databricks jobs list-runs --run-type SUBMIT_RUN` puis lire sa sortie.
