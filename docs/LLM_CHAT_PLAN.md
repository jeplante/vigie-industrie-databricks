# Assistant conversationnel Vigie - cadrage

## Décision

Le pilote utilise le modèle open source servi par Databricks
`databricks-gpt-oss-20b`. Le 7 septembre 2026, cet endpoint est `READY` et
une invocation de test a réussi dans le workspace. Il est appelé au moyen des Foundation Model APIs de
Databricks, et non par une clé OpenAI. Le navigateur ne reçoit jamais de jeton
Databricks ni d'accès direct à une table Unity Catalog.

## Architecture

```
Gold Viewer App -> endpoint chat serveur -> contexte SQL borné ->
Databricks Foundation Model API -> réponse JSON citée -> App
```

L'endpoint serveur authentifie l'appelant, limite le débit et effectue trois
lectures en lecture seule : comparaisons Gold, historique Silver et nouvelles
officielles. Il transmet seulement les lignes pertinentes à la question, la
compagnie et la période sélectionnées. Aucune recherche Web, aucune donnée
brute et aucun secret n'est inclus dans le prompt.

## Contrat de réponse

Le modèle produit obligatoirement un JSON avec `answer`, `citations` et
`caveat`. Chaque citation doit correspondre à une URL de document officiel
présente dans le contexte. Une réponse sans citation est refusée pour les
questions factuelles. Le système indique explicitement qu'il ne s'agit pas de
conseil financier et refuse de compléter une valeur absente ou non validée.
Le budget de sortie doit couvrir la phase de raisonnement et la réponse finale;
le pilote valide ce point avec des réponses structurées avant exposition dans
l'App.

## Garde-fous du pilote

- maximum 600 caractères par question et six messages d'historique;
- maximum 12 questions par minute et par utilisateur pseudonymisé;
- température basse, limite de sortie et contexte borné;
- journal d'audit sans contenu sensible : heure, compagnie, période, modèle,
  volume de tokens, statut et URLs citées;
- aucun appel IA pour l'extraction ou la publication des KPI.

## Évaluation avant activation

Un jeu d'évaluation couvre des questions de valeur, comparaison, historique,
provenance, données absentes et demandes de recommandation. Le pilote n'est
visible dans l'App qu'après validation de la fidélité des citations, de
l'absence d'hallucination et des limites de coût/quotas Free Edition.
