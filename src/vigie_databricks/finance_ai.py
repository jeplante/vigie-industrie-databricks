"""Strict, opt-in Finance AI fallback contract."""

from __future__ import annotations

import json
from typing import Any

from vigie_databricks.insurer_contract import InsurerContract, parse_finance_observation_candidate


def build_finance_ai_request(candidate: dict[str, Any], source_text: str, max_tokens: int = 256) -> dict[str, Any]:
    if not 1 <= max_tokens <= 512:
        raise ValueError("max_tokens must be between 1 and 512")
    return {
        "messages": [
            {"role": "system", "content": "Return only valid JSON with candidate and source_excerpt."},
            {"role": "user", "content": json.dumps({"candidate": candidate, "source_text": source_text[:12000]})},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }


def parse_finance_ai_output(content: str, contract: InsurerContract) -> dict[str, Any]:
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != {"candidate", "source_excerpt"}:
        raise ValueError("invalid_finance_ai_schema")
    if not isinstance(value["source_excerpt"], str) or not value["source_excerpt"].strip():
        raise ValueError("invalid_finance_ai_excerpt")
    candidate = value["candidate"]
    if not isinstance(candidate, dict):
        raise ValueError("invalid_finance_ai_candidate")
    parse_finance_observation_candidate(candidate, contract)
    return value


def invoke_finance_ai(
    candidate: dict[str, Any],
    source_text: str,
    contract: InsurerContract,
    *,
    enabled: bool,
    remaining_calls: int,
    invoke,
) -> dict[str, Any] | None:
    if not enabled or remaining_calls <= 0:
        return None
    response = invoke(build_finance_ai_request(candidate, source_text))
    if not isinstance(response, dict):
        raise ValueError("invalid_finance_ai_response")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("invalid_finance_ai_response")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ValueError("invalid_finance_ai_response")
    return parse_finance_ai_output(content, contract)