from __future__ import annotations

import importlib.util
from pathlib import Path


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

    monkeypatch.setattr(chat, "Config", ConfigStub)
    monkeypatch.setattr(chat.requests, "post", lambda *args, **kwargs: ResponseStub())

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
