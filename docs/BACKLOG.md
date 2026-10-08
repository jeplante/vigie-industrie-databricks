# Backlog d'idées

Idées pour améliorer la Vigie, classées par priorité. Une idée n'est pas un engagement : avant de la
réaliser, on confirme le besoin, la portée et les critères d'acceptation, puis elle devient une tranche de
travail normale (branche, tests, PR). Une idée réalisée ou abandonnée sort de la liste avec une ligne dans
« Historique ».

Chaque idée indique **Pourquoi** (le problème observé) et **Comment saurons-nous que c'est fait**.

## Priorité haute

Aucune idée pour le moment (les idées 1 et 2 sont réalisées, voir Historique).

## Priorité moyenne

### 4. Fiabiliser le chat
- **Pourquoi :** le contrôle des chiffres (`answer_check.py`) détecte un chiffre inventé, pas un vrai chiffre
  attribué au mauvais indicateur. Le chat vie ne voit que le dernier trimestre, alors que le chat P&C en
  voit six.
- **Fait quand :** un chiffre mal étiqueté est signalé, et le chat vie peut répondre sur l'historique.

### 6. Montrer les résultats semestriels d'Aviva Canada
- **Pourquoi :** Aviva Canada ne publie pas de trimestre isolé; la Vigie l'affiche N/A alors que des chiffres
  semestriels existent.
- **Fait quand :** une série semestrielle distincte est affichée, sans jamais la comparer à un trimestre.

## Priorité basse

### 8. Pertes catastrophiques P&C à partir des rapports de gestion
- **Pourquoi :** le montant trimestriel des pertes catastrophiques ne figure que dans le rapport de TD; Intact et
  Definity le donnent dans leur rapport de gestion (MD&A), un document que la Vigie ne lit pas encore, et en
  estimation préliminaire dans un communiqué en cours de trimestre.
- **Fait quand :** le rapport de gestion d'Intact et de Definity est acquis, le montant extrait et validé
  automatiquement pour les trois assureurs, et l'indicateur affiché.

### 7. Exercer le retour arrière de l'App
- **Pourquoi :** c'est la seule procédure de `docs/RUNBOOKS.md` jamais exécutée.
- **Fait quand :** un redéploiement volontaire d'une version sauvegardée, puis le retour à la version
  courante, sont faits un jour calme et notés dans le runbook.

## Historique
- 2026-10-07 : création du backlog.
- 2026-10-07 : idées 1 et 2 réalisées au-delà de leur portée. La publication P&C est entièrement automatique
  (`pnc_discovery.py` trouve les rapports, `pnc_auto_review.py` remplace la fiche de preuve manuelle) sur décision du
  user ; la fiche manuelle ne sert plus qu'aux exceptions.
- 2026-10-08 : idée 5 réalisée (alerte `news_stale` du monitor, actualités vie et P&C).
- 2026-10-08 : idée 3 close, absence expliquée dans l'App (pertes catastrophiques publiées par TD seul; ROE opérationnel sur douze mois glissants). Idée 8 ajoutée pour aller plus loin.
