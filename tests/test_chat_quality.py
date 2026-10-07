import importlib.util
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"
sys.path.insert(0, str(APP))

import answer_check  # noqa: E402
import chat_intents  # noqa: E402
import pnc_chat  # noqa: E402


# --- figure check ---------------------------------------------------------------------------------

CONTEXT = {
    "observations": [
        {"company_id": "DFY", "metric_id": "combined_ratio", "period_id": "2026-Q2", "value": 93.9, "unit": "PERCENT"},
        {"company_id": "DFY", "metric_id": "combined_ratio", "period_id": "2025-Q2", "value": 91.0, "unit": "PERCENT"},
        {"company_id": "DFY", "metric_id": "insurance_revenue", "period_id": "2026-Q2", "value": 1.7937, "unit": "CAD_BILLION"},
        {"company_id": "DFY", "metric_id": "net_income", "period_id": "2026-Q2", "value": 0.1524, "unit": "CAD_BILLION"},
    ]
}


def test_figures_traced_to_the_context_are_accepted_in_any_unit_and_format():
    text = ("Ratio combiné de 93,9 % (91,0 % un an plus tôt), soit +2,9 pp. Revenus de 1,79 $ B, "
            "résultat net de 152 M$ (0,15 G$), croissance de 3,2 % sur le ratio, et un trimestre clôturé le 30 juin 2026.")
    assert answer_check.unsupported_figures(text, CONTEXT) == []


def test_invented_figures_are_reported_and_dates_or_years_are_ignored():
    text = "Le ratio combiné est de 88,4 % et le résultat net de 320 millions, au 2026-Q2, le 30 juin, en 2025."
    assert answer_check.unsupported_figures(text, CONTEXT) == ["88,4 %", "320 millions"]
    assert answer_check.unsupported_figures("Aucun chiffre ici.", CONTEXT) == []
    assert answer_check.unsupported_figures("93,9 % et 93,9 %", {}) == ["93,9 %"]  # a figure with no context at all is unsupported, once


def test_ask_flags_unverified_figures_in_the_caveat_without_blocking_the_answer(monkeypatch):
    spec = importlib.util.spec_from_file_location("chat_service_quality", APP / "chat_service.py")
    chat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chat)

    class ConfigStub:
        host = "https://workspace.example"
        def authenticate(self): return {"Authorization": "Bearer t"}

    def respond(answer):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"choices": [{"message": {"content": json.dumps({"answer": answer, "citations": [], "used_kpis": [], "caveat": "prudence"})}}]}
        return Response()

    monkeypatch.setattr(chat, "Config", ConfigStub)
    monkeypatch.setattr(chat.requests, "post", lambda *a, **k: respond("Ratio combiné de 88,4 % pour DFY."))
    flagged = chat.ask("question", CONTEXT, [])
    assert flagged["unverified_figures"] == ["88,4 %"] and flagged["caveat"].startswith("prudence Vérification : ces chiffres")
    monkeypatch.setattr(chat.requests, "post", lambda *a, **k: respond("Ratio combiné de 93,9 % pour DFY."))
    clean = chat.ask("question", CONTEXT, [])
    assert "unverified_figures" not in clean and clean["caveat"] == "prudence"


# --- intents -------------------------------------------------------------------------------------------

def test_intents_answer_plain_questions_and_leave_explanations_to_the_model():
    intent = chat_intents.question_intent
    assert intent("quelle est la variation du ratio combine par rapport a lan dernier") == "variation"
    assert intent("classement des ratios de frais") == "ranking"
    assert intent("intact fait il mieux que definity") == "ranking"  # a head-to-head is a ranking of the two
    assert chat_intents.asks_for_explanation("pourquoi") and chat_intents.asks_for_explanation("que retenir des resultats")
    assert intent("qui a le meilleur ratio combine") == "ranking"
    assert intent("quelle compagnie a la meilleure solvabilite et pourquoi est ce important") is None  # asks for an explanation too
    assert intent("resume la variation du ratio combine") is None
    assert intent("quel est le resultat net de definity") is None


# --- P&C chat: variation and ranking ----------------------------------------------------------------

def obs(company, metric, period, value, unit="PERCENT", end="2026-06-30", basis="calendar"):
    return dict(company_id=company, metric_id=metric, period_id=period, value=value, unit=unit, period_end=end, calendar_basis=basis,
                disclosure_scope="s", source_url=f"https://example.com/{company}/{period}")


ROWS = [
    obs("IFC", "combined_ratio", "2026-Q2", 94.9), obs("IFC", "combined_ratio", "2025-Q2", 86.1, end="2025-06-30"),
    obs("DFY", "combined_ratio", "2026-Q2", 93.9), obs("DFY", "combined_ratio", "2025-Q2", 95.0, end="2025-06-30"),
    obs("TD", "net_income", "2026-Q2", 0.279, "CAD_BILLION", "2026-04-30", "fiscal"),
    obs("TD", "net_income", "2025-Q2", 0.227, "CAD_BILLION", "2025-04-30", "calendar"),  # prior year on another basis: not comparable
    obs("IFC", "net_income", "2026-Q2", 0.72, "CAD_BILLION"), obs("IFC", "net_income", "2025-Q2", 0.6, "CAD_BILLION", "2025-06-30"),
]


def ctx():
    return pnc_chat.compact_pnc_context(ROWS, [])


def test_pnc_variation_is_computed_against_the_same_quarter_and_basis_only():
    ans = pnc_chat.deterministic_answer("Quelle est la variation du ratio combiné par rapport à l'an dernier?", ctx())
    assert "IFC : 94.9 % vs 86.1 % en 2025-Q2 (▲ +8.8 pp)" in ans["answer"]
    assert "DFY : 93.9 % vs 95.0 % en 2025-Q2 (▼ -1.1 pp)" in ans["answer"]
    assert "AV : N/A (aucune valeur validée)" in ans["answer"]
    assert "neutre quant à ce qui est favorable" in ans["caveat"]
    blocked = pnc_chat.deterministic_answer("Variation du résultat net de TD par rapport à l'année précédente", ctx())
    assert "TD : variation annuelle N/A" in blocked["answer"] and "même base de calendrier" in blocked["answer"]  # fiscal vs calendar
    money = pnc_chat.deterministic_answer("évolution du résultat net d'Intact", ctx())
    assert "IFC : 0.720 G$ vs 0.600 G$ en 2025-Q2 (▲ +20.0 %)" in money["answer"]


def test_pnc_ranking_puts_the_most_favourable_ratio_first_and_keeps_na_visible():
    ans = pnc_chat.deterministic_answer("Quel assureur a le meilleur ratio combiné?", ctx())
    assert ans["answer"].startswith("Ratio combiné 2026-Q2, du plus favorable (le plus bas) au moins favorable — DFY : 93.9 %")
    assert ans["answer"].index("DFY") < ans["answer"].index("IFC") and "AV : N/A" in ans["answer"] and "TD : N/A" in ans["answer"]
    assert [kpi["company_id"] for kpi in ans["used_kpis"]] == ["DFY", "IFC"]
    amounts = pnc_chat.deterministic_answer("classement du résultat net", ctx())
    assert "du plus élevé au plus bas" in amounts["answer"] and amounts["answer"].index("IFC") < amounts["answer"].index("TD")  # an amount is ordered, not judged
    assert pnc_chat.deterministic_answer("Pourquoi Intact a le meilleur ratio combiné?", ctx()) is None  # explanation requested: model


# --- life chat: variation and ranking -------------------------------------------------------------------

def life_context():
    def row(company, metric, current, previous, previous_period="2025-Q2"):
        return {"company_id": company, "metric_id": metric, "current_period_id": "2026-Q2", "current_value": current,
                "previous_period_id": previous_period, "previous_value": previous}
    return {
        "comparisons": [row("MFC", "core_eps", 1.09, 0.95), row("SLF", "core_eps", 2.02, 1.79),
                        row("GWO", "core_eps", 1.5, 1.2, "2026-Q1"), row("MFC", "licat_ratio", 136.0, 136.0),
                        row("SLF", "licat_ratio", 145.0, 151.0), row("IAG", "licat_ratio", 137.0, 130.0)],
        "documents": [{"company_id": "SLF", "source_url": "https://example.com/slf"}], "news": [],
    }


def test_life_variation_is_year_over_year_only_and_ranking_is_ordered():
    chat_spec = importlib.util.spec_from_file_location("chat_service_intents", APP / "chat_service.py")
    chat = importlib.util.module_from_spec(chat_spec)
    chat_spec.loader.exec_module(chat)
    ctx_life = life_context()
    variation = chat.deterministic_answer("Quelle est la variation du BPA par rapport à l'an dernier?", ctx_life)
    assert "MFC : 1.09 vs 0.95 en 2025-Q2 (+14.7 %)" in variation["answer"] and "SLF : 2.02 vs 1.79 en 2025-Q2 (+12.8 %)" in variation["answer"]
    assert "GWO : variation annuelle N/A" in variation["answer"]  # previous period is the prior quarter, not the prior year
    pp = chat.deterministic_answer("variation du ratio LICAT vs l'année précédente", ctx_life)
    assert "SLF : 145.0 vs 151.0 en 2025-Q2 (-6.0 pp)" in pp["answer"] and "IAG : 137.0 vs 130.0 en 2025-Q2 (+7.0 pp)" in pp["answer"]
    ranking = chat.deterministic_answer("Quelle compagnie a le meilleur ratio LICAT?", ctx_life)
    assert ranking["answer"].startswith("Ratio de solvabilité, du plus élevé au moins élevé — SLF : 145.0") and ranking["answer"].index("IAG") < ranking["answer"].index("MFC")
    assert chat.deterministic_answer("Quelle compagnie a la meilleure solvabilité et pourquoi est-ce important?", ctx_life) is None
    lookup = chat.deterministic_answer("Quel est le BPA de Manuvie?", ctx_life)
    assert lookup["answer"].startswith("Bpa de base — MFC : 1.09")  # the plain lookup is unchanged
