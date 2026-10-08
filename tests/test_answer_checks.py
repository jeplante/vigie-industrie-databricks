"""Figure checks on chat answers, on sentences the real model wrote (2026-10-08 evaluation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/gold_viewer"))
from answer_check import misattributed_figures, mislabelled_figures, misscaled_figures  # noqa: E402

PNC = {"observations": [
    {"company_id": "IFC", "metric_id": "combined_ratio", "period_id": "2026-Q2", "value": 94.9, "unit": "PERCENT"},
    {"company_id": "IFC", "metric_id": "combined_ratio", "period_id": "2026-Q1", "value": 91.3, "unit": "PERCENT"},
    {"company_id": "IFC", "metric_id": "operating_income", "period_id": "2026-Q2", "value": 0.561, "unit": "CAD_BILLION"},
    {"company_id": "IFC", "metric_id": "net_income", "period_id": "2026-Q2", "value": 0.72, "unit": "CAD_BILLION"},
    {"company_id": "DFY", "metric_id": "combined_ratio", "period_id": "2026-Q2", "value": 93.9, "unit": "PERCENT"},
    {"company_id": "DFY", "metric_id": "claims_ratio", "period_id": "2026-Q2", "value": 64.2, "unit": "PERCENT"},
    {"company_id": "DFY", "metric_id": "expense_ratio", "period_id": "2026-Q2", "value": 29.7, "unit": "PERCENT"},
    {"company_id": "DFY", "metric_id": "insurance_revenue", "period_id": "2026-Q2", "value": 1.7937, "unit": "CAD_BILLION"},
    {"company_id": "DFY", "metric_id": "operating_income", "period_id": "2026-Q2", "value": 0.118, "unit": "CAD_BILLION"},
    {"company_id": "DFY", "metric_id": "net_income", "period_id": "2026-Q2", "value": 0.1524, "unit": "CAD_BILLION"},
    {"company_id": "TD", "metric_id": "net_income", "period_id": "2026-Q2", "value": 0.279, "unit": "CAD_BILLION"},
]}
LIFE = {"comparisons": [
    {"company_id": company, "metric_id": metric, "current_period_id": "2026-Q2", "current_value": value}
    for company, metric, value in (
        ("MFC", "core_roe", 16.3), ("SLF", "core_roe", 19.1), ("GWO", "core_roe", 19.3), ("IAG", "core_roe", 17.5),
        ("MFC", "core_eps", 1.09), ("IAG", "core_eps", 3.68), ("SLF", "core_earnings", 1.123), ("SLF", "net_income", 1.008),
        ("SLF", "assets_under_management", 1696.0), ("GWO", "total_client_assets", 3.711), ("GWO", "licat_ratio", 128.0))]}


def test_real_mislabels_are_flagged():
    assert mislabelled_figures("Le ratio de sinistres d'Intact est de 94,9 %.", PNC) == ["94,9 % (combined_ratio)"]
    td = "TD Insurance a généré un revenu d'assurance de 0,279 billion CAD."
    assert mislabelled_figures(td, PNC) == ["0,279 billion (net_income)"]
    assert mislabelled_figures("Le résultat net de Definity est de 118 M$.", PNC) == ["118 M$ (operating_income)"]
    yoy = "Cette hausse reflète une augmentation des ratios de sinistres (de 91,3 % à 94,9 %) et des frais d'Intact."
    assert mislabelled_figures(yoy, PNC) == ["91,3 % (combined_ratio)", "94,9 % (combined_ratio)"]


def test_correct_sentences_and_lists_are_not_flagged():
    for sentence in ("Definity : ratio combiné 93,9 %, sinistres 64,2 % et frais 29,7 %.",
                     "Le ratio combiné d'Intact est de 94,9 % et celui de Definity de 93,9 %.",
                     "Les ratios combinés, de sinistres et de frais de Definity sont respectivement 93,9 %, 64,2 % et 29,7 %.",
                     "Le résultat net consolidé s'élevait à 0,72 billion CAD, tandis que le revenu d'exploitation était de 0,561 billion CAD."):
        assert mislabelled_figures(sentence, PNC) == [], sentence
    assert mislabelled_figures("Le résultat net consolidé était de 0,1524 billion CAD, contre 1,7937 billion CAD de revenus d'assurance.", PNC) == []
    assert mislabelled_figures("Le résultat net d'exploitation d'Intact s'élevait à 0,561 billion CAD.", PNC) == []
    ranking = "un ratio de solvabilité (licat = 128 %) qui reste robuste, ce qui permet à GWO de générer un rendement plus élevé sur ses capitaux propres que ses concurrents (MFC = 16,3 %, SLF = 19,1 %, IAG = 17,5 %)."
    assert mislabelled_figures(ranking, LIFE) == []
    # "résultat d'exploitation" is the core earnings of a life insurer, not a P&C operating income
    assert mislabelled_figures("Sun Life a enregistré un résultat d'exploitation de 1,123 G$.", LIFE) == []
    assert mislabelled_figures("Sun Life ne publie pas ses actifs sous gestion, mais son revenu net de 1,008 G$ a augmenté.", LIFE) == []


def test_wrong_units_are_flagged_and_right_ones_pass():
    assert misscaled_figures("Le revenu d'assurance totalait 1,793 M CAD.", PNC) == []  # not a published amount at any scale
    assert misscaled_figures("Les revenus nets ont bondi à 1 008 M$.", LIFE) == []  # 1 008 M$ = 1,008 G$: right
    assert misscaled_figures("Les revenus nets ont atteint 1,008 M$.", LIFE) == ["1,008 M$"]
    assert misscaled_figures("Les actifs sous gestion atteignent 1 696 M$.", LIFE) == ["1 696 M$"]
    assert misscaled_figures("Great-West gère 3,71 milliards de dollars d'actifs clients.", LIFE) == ["3,71 milliards"]
    assert misscaled_figures("Great-West gère 3,711 T$ d'actifs clients.", LIFE) == []
    assert misscaled_figures("le bénéfice par action a progressé à 1,09 $ milliards", LIFE) == ["1,09 $ milliards"]
    assert misscaled_figures("le bénéfice par action est de 1,09 $.", LIFE) == []


def test_wrong_issuer_is_flagged_but_not_a_comparison():
    portrait = ("Intact Financial (IFC) a affiché un ratio combiné de 94,9 % et un revenu d'assurance de 1,7937 billion CAD. "
                "Son résultat net opérationnel s'élevait à 0,561 billion CAD. Definity Financial (DFY) a un ratio combiné de 93,9 %.")
    assert misattributed_figures(portrait, PNC) == ["1,7937 billion (DFY, pas IFC)"]
    for sentence in ("La ROE d'iA (IAG) est de 17,5 % tandis que celle de Manuvie (MFC) est de 16,3 %.",
                     "En 2026-Q2, Intact (94,9 %) et Definity (93,9 %) sont plus favorables que TD.",
                     "iA affiche un BPA de 3,68 $ contre 1,09 $ pour Manuvie.",
                     "En résumé, IFC et DFY présentent des ratios combinés proches (94,9 % et 93,9 %)."):
        assert misattributed_figures(sentence, PNC | LIFE) == [], sentence


def test_a_change_compared_with_the_wrong_quarter_is_flagged():
    from answer_check import misdated_figures

    life = {"observations": [{"company_id": "SLF", "metric_id": "net_income", "period_id": period, "value": value}
                             for period, value in (("2025-Q2", 0.716), ("2025-Q3", 1.106), ("2025-Q4", 0.722), ("2026-Q1", 0.465), ("2026-Q2", 1.008))]}
    wrong = "En 2026‑Q2, le net income s'élevait à 1,008 G$ (augmentation de 40,8 % par rapport à 2025‑Q4)."
    assert misdated_figures(wrong, life) == ["40,8 % (calculé contre 2025-Q2, pas 2025-Q4)"]
    assert misdated_figures("Il a progressé de 40,8 % par rapport au deuxième trimestre 2025.", life) == []
    assert misdated_figures("Il a progressé de 40,8 % vs T2 2025.", life) == []
    assert misdated_figures("Une hausse de 12 % par rapport à 2025-Q4.", life) == []  # explained by no pair: other checks decide
    assert misdated_figures("Le ratio combiné de 94,9 % est en hausse.", PNC) == []
