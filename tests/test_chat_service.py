from __future__ import annotations

import importlib.util
from pathlib import Path


class ArrayLike:
    def tolist(self):
        return [1.2, 3.4]


def _chat_service():
    path = Path(__file__).parents[1] / "apps" / "gold_viewer" / "chat_service.py"
    spec = importlib.util.spec_from_file_location("chat_service_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ask_extracts_text_from_gpt_oss_structured_content(monkeypatch):
    chat = _chat_service()

    class ConfigStub:
        host = "https://workspace.example"

        @staticmethod
        def authenticate():
            return {"Authorization": "Bearer token"}

    class ResponseStub:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '[{"type":"reasoning","summary":[]},'
                                '{"type":"text","text":"{\\"answer\\":\\"ready\\",'
                                '\\"citations\\":[{\\"label\\":\\"Report\\",\\"url\\":\\"https://official.example/report\\"}],'
                                '\\"caveat\\":null}"}]'
                            )
                        }
                    }
                ]
            }

    captured = {}

    def post(*args, **kwargs):
        captured.update(kwargs)
        return ResponseStub()

    monkeypatch.setattr(chat, "Config", ConfigStub)
    monkeypatch.setattr(chat.requests, "post", post)

    answer = chat.ask(
        "Est-ce prêt?",
        {"news": [], "documents": [{"source_url": "https://official.example/report"}]},
        [],
    )

    assert answer == {
        "answer": "ready",
        "citations": [{"label": "Report", "url": "https://official.example/report"}],
        "caveat": None,
    }


def test_ask_serializes_array_like_context(monkeypatch):
    chat = _chat_service()

    class ConfigStub:
        host = "https://workspace.example"

        @staticmethod
        def authenticate():
            return {}

    class ResponseStub:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"answer":"ok","citations":[],"caveat":null}'}}]}

    captured = {}
    monkeypatch.setattr(chat, "Config", ConfigStub)
    monkeypatch.setattr(chat.requests, "post", lambda *args, **kwargs: captured.update(kwargs) or ResponseStub())

    assert chat.ask("Montre les valeurs", {"values": ArrayLike(), "news": [], "documents": []}, []) ["answer"] == "ok"
    assert '"values": [1.2, 3.4]' in captured["json"]["messages"][0]["content"]


def test_compact_context_removes_unneeded_fields_and_bounds_news():
    chat = _chat_service()
    context = chat.compact_context(
        [{"company_id": "IAG", "metric_id": "net_income", "current_value": 123, "internal": "omit"}],
        [{"title": "A" * 500, "summary": "B" * 500, "source_url": "https://official.example/a"}] * 9,
        [{"company_id": "IAG", "reporting_period": "2026-Q2", "source_url": "https://official.example/q2", "hash": "omit"}],
    )

    assert context["comparisons"] == [{"company_id": "IAG", "metric_id": "net_income", "current_value": 123}]
    assert len(context["news"]) == 8
    assert len(context["news"][0]["summary"]) == 360
    assert context["documents"] == [{"company_id": "IAG", "reporting_period": "2026-Q2", "source_url": "https://official.example/q2"}]


def test_deterministic_answer_handles_simple_published_kpi_lookup():
    chat = _chat_service()
    answer = chat.deterministic_answer(
        "Compare les bénéfices de base des 4 assureurs pour Q2 2026",
        {"comparisons": [{"company_id": "MFC", "metric_id": "core_earnings", "current_value": 1.923, "current_period_id": "2026-Q2"}], "documents": [{"company_id": "MFC", "source_url": "https://official.example/mfc"}]},
    )
    assert answer and "MFC : 1.923 (2026-Q2)" in answer["answer"]
    assert answer["citations"][0]["url"] == "https://official.example/mfc"
