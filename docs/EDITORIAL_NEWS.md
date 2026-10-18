# Veille éditoriale

Les articles éditoriaux sont collectés dans `workspace.vigie.editorial_news`, séparément de `official_news` au niveau des données. Dans l’App, ils sont présentés avec les communiqués dans une seule section « Actualités », avec une étiquette indiquant le type de source. Ils ne modifient jamais les KPI Finance.

## Sources actives

- `insurance_journal`: flux RSS officiel, actualités assurance et P&C internationales.
- `insurance_canada`: flux RSS public canadien, technologie et industrie de l’assurance.
- `naifa_advisor_today`: publication professionnelle sur l’assurance-vie et le conseil financier.
- `artemis`: risques, réassurance et marché des capitaux d’assurance.

## Sources en attente de validation

- `advisor_ca` et `investment_executive`: pertinentes pour l’assurance-vie et la gestion de patrimoine, mais leurs flux ont répondu HTTP 403 au dry-run du 10 septembre 2026. Elles restent désactivées; aucun contournement anti-bot n’est permis.
- Journal de l’assurance / Insurance Portal: à ajouter uniquement après identification d’un flux public ou d’une autorisation explicite.

## Garde-fous

- HTTPS et hosts allowlistés;
- maximum 15 articles par source et par exécution;
- timeout, limite de taille et isolation des échecs par source;
- association MFC/SLF/GWO/IAG par termes déterministes seulement;
- étiquette « Source officielle » ou « Média sectoriel » dans l’App et lien vers l’article original;
- un article de média n’apparaît que sur la page de l’assureur qu’il nomme (même règle que le volet P&C); un article qui ne nomme aucun assureur vie n’est pas affiché. Depuis 2026-10-17 : avant, les articles généraux paraissaient sur chaque page, et les flux actuels (surtout P&C et américains) remplissaient les quatre pages d’articles sans rapport (0 article sur 181 ne nommait MFC, SLF, GWO ou IAG).
