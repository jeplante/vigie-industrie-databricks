"""Bounded, cited chat over already-published Vigie data."""
from __future__ import annotations

import json
import os
from typing import Any

import requests
from databricks.sdk.core import Config

DEFAULT_MODEL = "databricks-gpt-oss-20b"
SYSTEM = """You are Vigie, a French financial-information assistant. Answer only from CONTEXT.
Never invent values, dates, or sources; do not provide investment advice. Return strict JSON:
{"answer":"...","citations":[{"label":"...","url":"..."}],"caveat":"... or null"}.
Citations must use only URLs from CONTEXT. Cite at least one URL for factual answers."""


def _json_default(value: Any) -> Any:
    """Convert scalar and array values returned by the SQL/Pandas layer."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported context value: {type(value).__name__}")


def ask(question: str, context: dict[str, Any], history: list[dict[str, str]]) -> dict[str, Any]:
    if not 3 <= len(question.strip()) <= 600:
        raise ValueError("La question doit contenir entre 3 et 600 caractères.")
    config = Config()
    context_json = json.dumps(context, ensure_ascii=False, default=_json_default)
    messages = [{"role": "system", "content": SYSTEM + "\nCONTEXT:\n" + context_json}]
    messages.extend({"role": item["role"], "content": item["content"][:1200]} for item in history[-6:])
    messages.append({"role": "user", "content": question.strip()})
    response = requests.post(
        f"{config.host.rstrip('/')}/serving-endpoints/{os.environ.get('VIGIE_CHAT_ENDPOINT', DEFAULT_MODEL)}/invocations",
        headers={**config.authenticate(), "Content-Type": "application/json"},
        json={"messages": messages, "temperature": 0.1, "max_tokens": 768}, timeout=45,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if isinstance(content, str) and content.lstrip().startswith("["):
        structured_content = json.loads(content)
        if isinstance(structured_content, list):
            content = "".join(
                item.get("text", "")
                for item in structured_content
                if isinstance(item, dict) and item.get("type") == "text"
            )
    elif isinstance(content, list):
        content = "".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
    if not isinstance(content, str):
        raise ValueError("Model response is not text.")
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answer"), str):
        raise ValueError("Réponse du modèle non conforme.")
    allowed = {item.get("source_url") for item in context.get("news", [])} | {item.get("source_url") for item in context.get("documents", [])}
    parsed["citations"] = [item for item in parsed.get("citations", []) if isinstance(item, dict) and item.get("url") in allowed][:6]
    return parsed
