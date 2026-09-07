"""Bounded, cited chat over already-published Vigie data."""
from __future__ import annotations

import json
from typing import Any

import requests
from databricks.sdk.core import Config

MODEL = "databricks-gpt-oss-20b"
SYSTEM = """You are Vigie, a French financial-information assistant. Answer only from CONTEXT.
Never invent values, dates, or sources; do not provide investment advice. Return strict JSON:
{"answer":"...","citations":[{"label":"...","url":"..."}],"caveat":"... or null"}.
Citations must use only URLs from CONTEXT. Cite at least one URL for factual answers."""


def ask(question: str, context: dict[str, Any], history: list[dict[str, str]]) -> dict[str, Any]:
    if not 3 <= len(question.strip()) <= 600:
        raise ValueError("La question doit contenir entre 3 et 600 caractères.")
    config = Config()
    messages = [{"role": "system", "content": SYSTEM + "\nCONTEXT:\n" + json.dumps(context, ensure_ascii=False)}]
    messages.extend({"role": item["role"], "content": item["content"][:1200]} for item in history[-6:])
    messages.append({"role": "user", "content": question.strip()})
    response = requests.post(
        f"{config.host}/serving-endpoints/{MODEL}/invocations",
        headers={**config.authenticate(), "Content-Type": "application/json"},
        json={"messages": messages, "temperature": 0.1, "max_tokens": 768}, timeout=45,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        raise ValueError("Réponse du modèle non conforme.")
    allowed = {item.get("source_url") for item in context.get("news", [])} | {item.get("source_url") for item in context.get("documents", [])}
    parsed["citations"] = [item for item in parsed.get("citations", []) if isinstance(item, dict) and item.get("url") in allowed][:6]
    return parsed
