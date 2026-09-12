# Veille éditoriale

Les articles éditoriaux sont collectés dans `workspace.vigie.editorial_news`, séparément de `official_news`. Ils ne modifient ni les KPI Finance ni la liste des communiqués investisseurs.

## Sources actives

- `insurance_journal`: flux RSS officiel, actualités assurance et P&C internationales.

## Sources en attente de validation

- `advisor_ca` et `investment_executive`: pertinentes pour l’assurance-vie et la gestion de patrimoine, mais leurs flux ont répondu HTTP 403 au dry-run du 10 septembre 2026. Elles restent désactivées; aucun contournement anti-bot n’est permis.
- Journal de l’assurance / Insurance Portal: à ajouter uniquement après identification d’un flux public ou d’une autorisation explicite.

## Garde-fous

- HTTPS et hosts allowlistés;
- maximum 15 articles par source et par exécution;
- timeout, limite de taille et isolation des échecs par source;
- association MFC/SLF/GWO/IAG par termes déterministes seulement;
- étiquette « Veille sectorielle » dans l’App et lien vers l’article original.
