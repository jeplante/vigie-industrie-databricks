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