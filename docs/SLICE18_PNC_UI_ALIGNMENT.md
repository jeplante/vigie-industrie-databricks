# Slice 18 — Alignement du design P&C sur l'expérience Assurance de personnes

**Statut :** proposée
**Date :** 2026-10-06
**Dépendances :** P&C phase 1 slice 5 (sélecteur de domaine et présentation P&C),
Slice 13 (publication Finance atomique et fraîcheur), Slice 16 (expérience App).
**Domaine :** transverse — App `apps/gold_viewer`, les deux univers.

## 1. Problème

L'App sert deux univers par un sélecteur (`Assurance vie` / `Assurance de
dommages`), mais les deux ne partagent pas le même système visuel.

- **Assurance de personnes (life)** — `comparison_table.py` : en-tête
  `vigie-header`, table HTML avec couleur de marque par assureur
  (`--company-colour`), puce de période, delta YoY avec symbole ▲/▼ et
  tonalité, libellé de période de comparaison, infobulles d'aide sur chaque
  métrique, attributs d'accessibilité (`scope`).
- **Assurance de dommages (P&C)** — `pnc_view.py` : `st.title` et
  `st.dataframe` bruts, aucune couleur de marque, aucun delta, aucune
  infobulle; la branche est protégée par `PNC_PREVIEW_ENABLED` et se termine
  par `st.stop()`. C'est un aperçu parallèle, pas une expérience intégrée.

Un utilisateur qui bascule d'un univers à l'autre change de produit visuel, pas
seulement de données.

## 2. Principe non négociable de cette slice

**Aligner le système visuel ne doit jamais aplatir les vérités de domaine du
P&C.** La table life suppose une comparabilité trimestrielle directe (même
période, YoY légitime). Le P&C ne l'a pas, et c'est voulu :

- clôtures fiscales (TD) vs civiles, dates de clôture divergentes entre
  assureurs;
- résultats semestriels seulement (Aviva HY 2026) — jamais présentés comme un
  trimestre isolé;
- périmètres non comparables : groupe consolidé (IFC, DFY) vs segment (AV, TD);
- résultat opérationnel non-IFRS propre à chaque assureur.

Les colonnes `Périmètre`, `Calendrier`, `Clôture`, les avertissements de
clôtures divergentes et la sémantique `N/A` (« aucune valeur validée », pas
« rien communiqué ») restent des citoyens de première classe. Appliquer le
gabarit life sans ces garde-fous réintroduirait la fausse comparabilité que le
P&C a été conçu pour refuser. Cette slice est un **refactor vers des composants
partagés**, pas un copier-coller du rendu life.

## 3. Inclure

- **Extraire un module de présentation partagé** (p. ex.
  `apps/gold_viewer/shared_ui.py`) portant ce qui est réellement commun :
  l'en-tête `vigie-header` paramétré (eyebrow, titre, sous-titre), la coquille
  de table de comparaison à couleur de marque, le formatage de valeur, la puce
  de période et les infobulles. `comparison_table.py` et le rendu P&C
  consomment ce module au lieu de diverger.
- **Registre de marque unifié** : une seule source pour `(nom, couleur)` par
  assureur, étendue aux quatre émetteurs P&C (IFC, AV, TD, DFY). Aujourd'hui la
  couleur vit dans `COMPANIES` de `comparison_table.py`; le P&C n'en a pas.
- **Rendre P&C par la table à couleur de marque**, avec les colonnes de
  domaine P&C conservées (Périmètre, Calendrier, Clôture) intégrées au même
  composant, pas en `st.dataframe` séparé.
- **Formatage de valeur réconcilié** : une convention unique (p. ex. `G$`
  vs `G$ CA`, décimales des ratios) exposée par le module partagé et appliquée
  aux deux univers.
- **YoY conditionnel et honnête côté P&C** : afficher un delta uniquement quand
  une comparaison même-période de l'année précédente est légitime (même
  calendrier, même périmètre, période trimestrielle réelle). Sinon, pas de
  delta — jamais un delta trompeur. Réutiliser la logique
  `expected_yoy_period` / garde de `previous_period_id` de `comparison_table`.
- **Promouvoir le P&C de preview à univers intégré** : retirer le `st.stop()`
  de cul-de-sac et faire passer le P&C par la même ossature de page (en-tête,
  barre latérale d'état des sources adaptée, pied de notes) que le life.
  Le flag `PNC_PREVIEW_ENABLED` peut rester le gate d'activation, mais la
  branche active rend une page complète, pas un aperçu.
- **Parité d'accessibilité** : attributs `scope`, titres d'infobulle et
  contrastes identiques dans les deux univers; `style.css` étendu sans
  duplication de règles.

## 4. Ne pas inclure

- Aucune nouvelle acquisition, extraction ou publication de données : cette
  slice est strictement présentation. Les tables Gold P&C et life restent
  inchangées.
- Aucune fusion des domaines de données : les tables P&C et life demeurent
  séparées (principe du `PNC_BUILD_PLAN`). On partage des composants d'UI, pas
  des tables.
- Aucun changement au service de clavardage ni aux contrats de données.
- Aucune harmonisation des KPI eux-mêmes : les métriques P&C (ratio combiné,
  ratio de sinistres…) et life (BPA de base, LICAT…) restent distinctes.

## 5. Décision humaine avant exécution

- Confirmer la palette de marque des quatre émetteurs P&C (IFC, AV, TD, DFY) —
  couleurs non encore définies, à valider pour cohérence et contraste.
- Confirmer la convention de formatage unique (unités, décimales) à imposer aux
  deux univers.
- Confirmer que le P&C passe de preview à univers pleinement intégré dès cette
  slice, ou reste derrière `PNC_PREVIEW_ENABLED` jusqu'à une acceptation
  séparée.

## 6. Sortie

Les deux univers se lisent comme un seul produit : même en-tête, même table à
couleur de marque, même formatage, mêmes infobulles et même accessibilité — et
le P&C conserve intégralement ses colonnes Périmètre / Calendrier / Clôture,
ses avertissements de clôtures divergentes, sa sémantique `N/A` et ses deltas
seulement lorsqu'une comparaison est légitime. Le code de présentation commun
vit dans un module unique consommé par les deux univers; `comparison_table.py`
et `pnc_view.py` n'ont plus de rendu visuel dupliqué.

## 7. Tests

- Tests de rendu HTML du composant partagé : en-tête, coquille de table,
  formatage, pour des lignes life et P&C.
- Test de non-régression P&C : les colonnes Périmètre / Calendrier / Clôture et
  l'avertissement de clôtures divergentes sont présents dans le rendu intégré.
- Test de garde YoY P&C : aucun delta n'est émis quand `previous_period_id` ne
  correspond pas à la même période de l'année précédente, ni entre calendriers
  ou périmètres différents.
- Test de parité d'accessibilité : présence des attributs `scope` et des titres
  d'infobulle dans les deux univers.
- Aucun test ne déclenche d'accès réseau; fixtures seulement.
