# Backlog d'idées

Idées pour améliorer la Vigie, classées par priorité. Une idée n'est pas un engagement : avant de la
réaliser, on confirme le besoin, la portée et les critères d'acceptation, puis elle devient une tranche de
travail normale (branche, tests, PR). Une idée réalisée ou abandonnée sort de la liste avec une ligne dans
« Historique ».

Chaque idée indique **Pourquoi** (le problème observé) et **Comment saurons-nous que c'est fait**.

## Priorité haute

Aucune idée pour le moment (les idées 1 et 2 sont réalisées, voir Historique).

## Priorité moyenne

### 3. Afficher les indicateurs P&C déjà définis mais absents de l'App
- **Pourquoi :** `config/pnc/metrics.yaml` définit les pertes catastrophiques et le rendement des capitaux
  propres opérationnel, mais l'App ne les montre pas.
- **Fait quand :** ces indicateurs sont extraits, validés, publiés et affichés, ou leur absence est expliquée.

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
- 2026-10-07 : idées 1 et 2 réalisées au-delà de leur portée. La publication P&C est entièrement automatique
  (`pnc_discovery.py` trouve les rapports, `pnc_auto_review.py` remplace la fiche de preuve manuelle) sur décision du
  user ; la fiche manuelle ne sert plus qu'aux exceptions.
