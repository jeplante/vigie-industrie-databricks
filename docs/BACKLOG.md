# Backlog d'idées

Idées pour améliorer la Vigie, classées par priorité. Une idée n'est pas un engagement : avant de la
réaliser, on confirme le besoin, la portée et les critères d'acceptation, puis elle devient une tranche de
travail normale (branche, tests, PR). Une idée réalisée ou abandonnée sort de la liste avec une ligne dans
« Historique ».

Chaque idée indique **Pourquoi** (le problème observé) et **Comment saurons-nous que c'est fait**.

## Priorité haute

### 1. Trouver automatiquement le rapport trimestriel P&C d'un nouveau trimestre
- **Aujourd'hui :** quand un assureur P&C publie ses résultats, il faut chercher à la main le lien du
  rapport, l'écrire dans un manifeste (`config/pnc/history/<trimestre>.yaml`) et lancer l'acquisition. Le
  monitor signale déjà qu'un trimestre manque, mais ne dit pas où est le rapport.
- **Idée :** trouver ce lien tout seul. Le rapport TD suit un modèle d'adresse prévisible
  (`.../quarterly-results/<année>/q<n>/<année>-q<n>-report-shareholders-en.pdf`). Intact et Definity
  annoncent leurs résultats par un communiqué, que le Job d'actualités P&C lit déjà.
- **Ce qui ne change pas :** une personne valide toujours le chiffre avant sa publication. C'est une règle du
  dépôt : un chiffre P&C n'est publié qu'après relecture de la preuve. L'automatisation retire la recherche
  du document, pas la validation.
- **Fait quand :** pour un nouveau trimestre, le manifeste et l'acquisition se font sans saisie manuelle de
  lien, et la revue démarre directement sur un candidat extrait.

### 2. Générer un brouillon de fiche de preuve
- **Aujourd'hui :** la fiche de `config/pnc/reviewed_evidence.yaml` s'écrit à la main (empreinte du document,
  page, tableau, extrait, période), comme pour TD 2026-Q3 le 2026-10-07.
- **Idée :** un script qui produit ce brouillon à partir du candidat acquis et de la page du PDF, avec les
  recoupements automatiques (variation sur un an et sur le trimestre, cumul de l'exercice) déjà calculés.
- **Fait quand :** la revue d'un trimestre se résume à lire le brouillon et ses recoupements, puis à approuver.

## Priorité moyenne

### 3. Afficher les indicateurs P&C déjà définis mais absents de l'App
- **Pourquoi :** `config/pnc/metrics.yaml` définit les pertes catastrophiques et le rendement des capitaux
  propres opérationnel, mais l'App ne les montre pas.
- **Fait quand :** ces indicateurs sont extraits, revus, publiés et affichés, ou leur absence est expliquée.

### 4. Fiabiliser le chat
- **Pourquoi :** le contrôle des chiffres (`answer_check.py`) détecte un chiffre inventé, pas un vrai chiffre
  attribué au mauvais indicateur. Le chat vie ne voit que le dernier trimestre, alors que le chat P&C en
  voit six.
- **Fait quand :** un chiffre mal étiqueté est signalé, et le chat vie peut répondre sur l'historique.

### 5. Alerte de fraîcheur des actualités vie dans le monitor
- **Pourquoi :** seule la barre latérale de l'App montre qu'une source d'actualités vie est en retard;
  personne n'est prévenu par courriel.
- **Fait quand :** le monitor alerte quand aucune actualité vie n'a été collectée depuis un délai défini.

### 6. Montrer les résultats semestriels d'Aviva Canada
- **Pourquoi :** Aviva Canada ne publie pas de trimestre isolé; la Vigie l'affiche N/A alors que des chiffres
  semestriels existent.
- **Fait quand :** une série semestrielle distincte est affichée, sans jamais la comparer à un trimestre.

## Priorité basse

### 7. Exercer le retour arrière de l'App
- **Pourquoi :** c'est la seule procédure de `docs/RUNBOOKS.md` jamais exécutée.
- **Fait quand :** un redéploiement volontaire d'une version sauvegardée, puis le retour à la version
  courante, sont faits un jour calme et notés dans le runbook.

## Historique
- 2026-10-07 : création du backlog.
