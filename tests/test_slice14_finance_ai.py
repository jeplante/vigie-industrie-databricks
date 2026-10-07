from pathlib import Path
import pytest
from vigie_databricks.finance_ai import build_finance_ai_request, invoke_finance_ai, parse_finance_ai_output
from vigie_databricks.insurer_contract import load_insurer_contract
ROOT = Path(__file__).resolve().parents[1]
def test_finance_ai_output_requires_a_valid_candidate_and_excerpt():
    payload = '{"candidate":{"observation_id":"MFC-2026-Q1-core_earnings","company_id":"MFC","metric_id":"core_earnings","period_id":"2026-Q1","value":1.8,"unit":"CAD_BILLION","source_url":"https://www.manulife.com/ca/en/about-us/investors/results-and-reports","source_document_hash":"x","quality_status":"candidate"},"source_excerpt":"Core earnings were reported."}'
    assert parse_finance_ai_output(payload, load_insurer_contract(ROOT / "config"))["candidate"]["company_id"] == "MFC"
    with pytest.raises(ValueError, match="schema"):
        parse_finance_ai_output("{}", load_insurer_contract(ROOT / "config"))


def test_finance_ai_request_is_deterministic_and_bounded():
    request = build_finance_ai_request({"company_id": "MFC"}, "x" * 13000)
    assert request["max_tokens"] == 256
    assert request["temperature"] == 0
    assert len(request["messages"][1]["content"]) < 13000


def test_finance_ai_invocation_is_opt_in_and_budget_aware():
    contract = load_insurer_contract(ROOT / "config")
    calls = []
    assert invoke_finance_ai({}, "text", contract, enabled=False, remaining_calls=1, invoke=calls.append) is None
    assert invoke_finance_ai({}, "text", contract, enabled=True, remaining_calls=0, invoke=calls.append) is None
    assert calls == []


def _ai_response(candidate, excerpt):
    import json
    return {"choices": [{"message": {"content": json.dumps({"candidate": candidate, "source_excerpt": excerpt})}}]}


def test_finance_ai_may_only_fill_the_requested_candidate_value():
    contract = load_insurer_contract(ROOT / "config")
    skeleton = {"observation_id": "MFC-2026-Q1-licat_ratio", "company_id": "MFC", "metric_id": "licat_ratio",
                "period_id": "2026-Q1", "value": 0.0, "unit": contract.metrics["licat_ratio"].unit,
                "source_url": "https://www.manulife.com/ca/en/about-us/investors/results-and-reports",
                "source_document_hash": "x", "quality_status": "candidate"}
    text = "The LICAT ratio was 140%."
    filled = dict(skeleton, value=140.0)
    parsed = invoke_finance_ai(skeleton, text, contract, enabled=True, remaining_calls=1,
                               invoke=lambda payload: _ai_response(filled, "LICAT ratio was 140%"))
    assert parsed["candidate"]["value"] == 140.0

    other_period = dict(filled, observation_id="MFC-2025-Q4-licat_ratio", period_id="2025-Q4")
    with pytest.raises(ValueError, match="identity"):
        invoke_finance_ai(skeleton, text, contract, enabled=True, remaining_calls=1,
                          invoke=lambda payload: _ai_response(other_period, "LICAT ratio was 140%"))
