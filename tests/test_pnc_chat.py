import importlib.util
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

APP = Path(__file__).resolve().parents[1] / "apps" / "gold_viewer"
sys.path.insert(0, str(APP))

import pnc_chat  # noqa: E402


def obs(company, metric, period, value, unit="PERCENT", end="2026-06-30", basis="calendar", url=None):
    return dict(company_id=company, metric_id=metric, period_id=period, value=value, unit=unit, period_end=end,
                calendar_basis=basis, disclosure_scope="s", source_url=url or f"https://example.com/{company}/{period}")


ROWS = [
    obs("IFC", "combined_ratio", "2026-Q2", 94.9), obs("IFC", "net_income", "2026-Q2", 0.72, "CAD_BILLION"),
    obs("DFY", "combined_ratio", "2026-Q2", 93.9), obs("DFY", "net_income", "2026-Q2", 0.1524, "CAD_BILLION"),
    obs("TD", "net_income", "2026-Q2", 0.279, "CAD_BILLION", "2026-04-30", "fiscal"),
    obs("IFC", "combined_ratio", "2025-Q2", 86.1, end="2025-06-30"),
    obs("IFC", "combined_ratio", "2024-Q1", 90.0, end="2024-03-31"),
]
NEWS = [{"company_id": "IFC", "title": "Q3 catastrophe loss estimate", "published_at": None, "summary": "x" * 500, "source_url": "https://newsroom.intactfc.com/a"}]


def context(max_periods=6):
    return pnc_chat.compact_pnc_context(ROWS, NEWS, max_periods)


def test_context_keeps_recent_quarters_bounds_news_and_carries_the_gap_notes():
    ctx = context(max_periods=2)
    assert {row["period_id"] for row in ctx["observations"]} == {"2026-Q2", "2025-Q2"}  # 2024-Q1 falls outside the window
    assert ctx["observations"][0]["period_id"] == "2026-Q2"  # newest first
    assert len(ctx["news"][0]["summary"]) == 360 and ctx["news"][0]["company_ids"] == ["IFC"]
    assert any("Aviva" in note for note in ctx["notes"]) and any("non-IFRS" in note for note in ctx["notes"])
    assert {document["source_url"] for document in ctx["documents"]} >= {"https://example.com/IFC/2026-Q2"}
    assert ("IFC", "combined_ratio", "2026-Q2") in pnc_chat.allowed_kpis(ctx)
    assert pnc_chat.compact_pnc_context([{"company_id": "X", "period_id": "annual"}], [])["observations"] == []


def test_deterministic_answer_compares_issuers_with_closing_dates_and_na():
    ans = pnc_chat.deterministic_answer("Compare les ratios combinés des assureurs pour le dernier trimestre", context())
    assert ans["answer"].startswith("Ratio combiné 2026-Q2 —")
    assert "IFC : 94.9 % (clôture 2026-06-30, civil)" in ans["answer"] and "DFY : 93.9 %" in ans["answer"]
    assert "AV : N/A (aucune valeur validée)" in ans["answer"] and "TD : N/A" in ans["answer"]
    assert ans["caveat"].startswith("Un ratio plus bas est plus favorable")
    assert {c["url"] for c in ans["citations"]} == {"https://example.com/IFC/2026-Q2", "https://example.com/DFY/2026-Q2"}
    assert {k["company_id"] for k in ans["used_kpis"]} == {"IFC", "DFY"}


def test_deterministic_answer_understands_company_period_basis_and_the_operating_measure():
    one = pnc_chat.deterministic_answer("Quel est le résultat net de TD Insurance au T2 2026?", context())
    assert one["answer"] == "Résultat net 2026-Q2 — TD : 0.279 G$ (clôture 2026-04-30, fiscal)."
    assert pnc_chat.deterministic_answer("résultat net opérationnel d'Intact", context())["answer"].startswith("Aucune valeur publiée")
    earlier = pnc_chat.deterministic_answer("ratio combiné d'Intact en 2025-Q2", context())
    assert "IFC : 86.1 % (clôture 2025-06-30, civil)" in earlier["answer"] and "caveat" in earlier
    assert pnc_chat.deterministic_answer("Quel temps fait-il?", context()) is None
    missing = pnc_chat.deterministic_answer("ratio combiné d'Aviva", context())
    assert missing["citations"] == [] and "Aucune valeur publiée" in missing["answer"]


def test_fallback_uses_only_published_combined_ratios():
    ans = pnc_chat.fallback_answer(context())
    assert "indisponible" in ans["answer"] and "IFC : 94.9 %" in ans["answer"] and "(2026-Q2)" in ans["answer"]
    empty = pnc_chat.fallback_answer({"observations": []})
    assert empty["citations"] == [] and "aucun ratio combiné" in empty["answer"]


def _chat_service():
    path = APP / "chat_service.py"
    spec = importlib.util.spec_from_file_location("chat_service_for_pnc", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ask_uses_the_pnc_prompt_and_validates_citations_and_kpis(monkeypatch):
    chat = _chat_service()
    sent = {}

    class ConfigStub:
        host = "https://workspace.example"
        def authenticate(self): return {"Authorization": "Bearer t"}

    class Response:
        def raise_for_status(self): pass
        def json(self):
            answer = {"answer": "IFC 94,9 %", "citations": [{"label": "ok", "url": "https://example.com/IFC/2026-Q2"}, {"label": "invented", "url": "https://evil.example/x"}],
                      "used_kpis": [{"company_id": "IFC", "metric_id": "combined_ratio", "period_id": "2026-Q2"}, {"company_id": "IFC", "metric_id": "combined_ratio", "period_id": "2030-Q1"}], "caveat": None}
            return {"choices": [{"message": {"content": json.dumps(answer)}}]}

    monkeypatch.setattr(chat, "Config", ConfigStub)
    monkeypatch.setattr(chat.requests, "post", lambda url, **kwargs: sent.update(kwargs) or Response())
    ctx = context()
    out = chat.ask("question", ctx, [], system=pnc_chat.PNC_SYSTEM, allowed_kpis=pnc_chat.allowed_kpis(ctx))
    prompt = sent["json"]["messages"][0]["content"]
    assert prompt.startswith("You are Vigie, a French financial-information assistant for four Canadian P&C insurers") and "CONTEXT:" in prompt
    assert [c["url"] for c in out["citations"]] == ["https://example.com/IFC/2026-Q2"]  # the invented URL is dropped
    assert out["used_kpis"] == [{"company_id": "IFC", "metric_id": "combined_ratio", "period_id": "2026-Q2"}]  # the unknown period is dropped
    assert sent["json"]["max_tokens"] == 1536 and sent["json"]["temperature"] == 0.1
    assert "reasoning_effort" not in sent["json"]  # the default call is unchanged (life chat)
    chat.ask("question", ctx, [], system=pnc_chat.PNC_SYSTEM, allowed_kpis=pnc_chat.allowed_kpis(ctx), reasoning_effort="low")
    assert sent["json"]["reasoning_effort"] == "low"


def _load_view():
    path = APP / "pnc_view.py"
    spec = importlib.util.spec_from_file_location("pnc_view_for_chat", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChatView:
    def __init__(self, question=None, click=None):
        self.session_state, self.question, self.click = {}, question, click
        self.writes, self.warnings, self.captions, self.links, self.input_keys = [], [], [], [], []

    def divider(self): pass
    def markdown(self, text, **kwargs): pass
    def subheader(self, text): pass
    def caption(self, text): self.captions.append(text)
    def write(self, text): self.writes.append(text)
    def warning(self, text): self.warnings.append(text)
    def spinner(self, text): return nullcontext()
    def chat_message(self, role): return nullcontext()
    def link_button(self, label, url, key=None): self.links.append((url, key))
    def chat_input(self, placeholder, key=None):
        self.input_keys.append(key)
        return self.question

    def columns(self, count):
        owner = self
        return [SimpleNamespace(button=lambda label, **kw: label == owner.click) for _ in range(count)]


def test_chat_ui_answers_locally_keeps_its_own_conversation_and_never_calls_the_model():
    module = _load_view()
    view = ChatView(question="Quel est le résultat net de Definity?")
    module.render_pnc_chat(view, ROWS, NEWS, ask_fn=lambda *a, **k: pytest.fail("a plain lookup must not reach the model"))
    assert any(text.startswith("Résultat net 2026-Q2 — DFY : 0.152 G$") for text in view.writes)
    assert [m["role"] for m in view.session_state["pnc_chat_messages"]] == ["user", "assistant"]
    assert "chat_messages" not in view.session_state  # the life conversation key is untouched
    assert any(key.startswith("pnc-chat-") for _, key in view.links) and view.input_keys == ["pnc-chat-input"]


def test_chat_ui_calls_the_model_with_the_pnc_prompt_for_open_questions_and_falls_back_on_failure():
    module = _load_view()
    seen = {}

    def model(question, ctx, history, **kwargs):
        seen.update(kwargs, question=question, history=history)
        return {"answer": "Réponse du modèle", "citations": [{"label": "Rapport", "url": "https://example.com/IFC/2026-Q2"}], "used_kpis": [], "caveat": "prudence"}

    view = ChatView(question="Que retenir des résultats?")
    module.render_pnc_chat(view, ROWS, NEWS, ask_fn=model)
    assert "Réponse du modèle" in view.writes and "prudence" in view.captions
    assert seen["system"] == pnc_chat.PNC_SYSTEM and ("IFC", "combined_ratio", "2026-Q2") in seen["allowed_kpis"] and seen["history"] == []
    assert seen["reasoning_effort"] == "low"  # a reasoning model must not spend its whole budget thinking

    def broken(*args, **kwargs):
        raise RuntimeError("endpoint unavailable")

    failing = ChatView(question="Que retenir des résultats?")
    module.render_pnc_chat(failing, ROWS, NEWS, ask_fn=broken)
    assert failing.warnings and "indisponible" in failing.warnings[0] and "IFC : 94.9 %" in failing.warnings[0]
    assert failing.session_state["pnc_chat_messages"][-1]["role"] == "assistant"


def test_chat_example_button_asks_the_example_question():
    module = _load_view()
    view = ChatView(question=None, click="Compare les ratios combinés des assureurs pour le dernier trimestre")
    module.render_pnc_chat(view, ROWS, NEWS, ask_fn=lambda *a, **k: pytest.fail("should be answered locally"))
    assert any(text.startswith("Ratio combiné 2026-Q2 —") for text in view.writes)


def test_known_gaps_are_explained_from_the_notes_without_the_model():
    ctx = context()
    aviva = pnc_chat.deterministic_answer("Pourquoi Aviva Canada est-il N/A?", ctx)
    assert aviva["answer"] == pnc_chat.NOTES[0] and aviva["citations"][0]["url"] == pnc_chat.AVIVA_HY26_URL
    assert "pas qu'Aviva n'a rien communiqué" in aviva["caveat"]
    also = pnc_chat.deterministic_answer("pourquoi le ratio combiné d'Aviva manque?", ctx)
    assert also["answer"] == pnc_chat.NOTES[0]  # the gap explanation wins over a metric lookup
    td = pnc_chat.deterministic_answer("Pourquoi TD Insurance a seulement le résultat net?", ctx)
    assert td["answer"] == pnc_chat.NOTES[1] and td["citations"][0]["url"].endswith("/TD/2026-Q2")
    assert pnc_chat.deterministic_answer("Pourquoi Definity va si bien?", ctx) is None  # no known gap: left to the model
    assert "empty list" in pnc_chat.PNC_SYSTEM and "at least one URL" not in pnc_chat.PNC_SYSTEM
