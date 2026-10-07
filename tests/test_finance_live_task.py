from __future__ import annotations

import json
import sys
from pathlib import Path

from vigie_databricks.finance_live import LiveFinanceResult
from vigie_databricks.tasks import finance_live as task


ROOT = Path(__file__).resolve().parents[1]


class FakeCatalog:
    @staticmethod
    def tableExists(_name):
        return False


class FakeSpark:
    catalog = FakeCatalog()


class FakeSparkSession:
    class builder:
        @staticmethod
        def getOrCreate():
            return FakeSpark()


def test_live_ai_fallback_requests_each_missing_metric_within_the_run_budget(monkeypatch, capsys):
    requested = []

    def fake_invoke(skeleton, *args, **kwargs):
        requested.append((skeleton["company_id"], skeleton["metric_id"]))
        return {"candidate": dict(skeleton, value=1.0), "source_excerpt": "x"}

    def fake_acquire(contract, prior, *, persist_raw, ai_fallback):
        metrics = ["core_earnings", "core_eps", "core_roe", "licat_ratio", "net_income", "total_client_assets"]
        returned = [
            ai_fallback(company_id, "2026-Q1", "https://example.invalid/report.pdf", "hash", "text", metrics)
            for company_id in ("GWO", "SLF")
        ]
        assert [len(candidates) for candidates in returned] == [6, 4]
        return LiveFinanceResult((), (), 4, {}, 0, 0, 0)

    monkeypatch.setattr(task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(task, "invoke_finance_ai", fake_invoke)
    monkeypatch.setattr(task, "acquire_live_finance", fake_acquire)
    monkeypatch.setattr(sys, "argv", [
        "finance_live", "--config-directory", str(ROOT / "config"),
        "--documents-object", "c.s.documents", "--bronze-object", "c.s.bronze",
        "--silver-object", "c.s.silver", "--gold-object", "c.s.gold",
        "--audit-object", "c.s.audit", "--run-id", "run-1", "--dry-run", "true",
    ])

    task.main()

    assert len(requested) == 10
    assert json.loads(capsys.readouterr().out)["audit"]["ai_model_calls"] == 10


def test_live_reconciliation_failure_records_a_stale_audit(monkeypatch):
    from dataclasses import dataclass

    import pytest

    @dataclass(frozen=True)
    class LayerResult:
        reconciliation_delta: int = 0

    audits = []
    publication = type("Publication", (), {"quality_status": "current", "observations": ({"observation_id": "o"},)})()
    monkeypatch.setattr(task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(task, "enforce_finance_retention", lambda *args, **kwargs: 0)
    monkeypatch.setattr(task, "acquire_live_finance", lambda *args, **kwargs: LiveFinanceResult((), ({"observation_id": "o"},), 4, {}, 0, 0, 0))
    monkeypatch.setattr(task, "upsert_financial_documents", lambda *args: None)
    monkeypatch.setattr(task, "publish_finance_candidates", lambda *args: publication)
    monkeypatch.setattr(task, "load_bronze_observations", lambda *args: LayerResult())
    monkeypatch.setattr(task, "load_silver_observations", lambda *args: LayerResult())
    monkeypatch.setattr(task, "load_gold_observations", lambda *args: LayerResult(reconciliation_delta=2))
    monkeypatch.setattr(task, "upsert_finance_run_audit", lambda spark, name, audit: audits.append(dict(audit)))
    monkeypatch.setattr(sys, "argv", [
        "finance_live", "--config-directory", str(ROOT / "config"),
        "--documents-object", "c.s.documents", "--bronze-object", "c.s.bronze",
        "--silver-object", "c.s.silver", "--gold-object", "c.s.gold",
        "--audit-object", "c.s.audit", "--run-id", "run-1", "--dry-run", "false",
    ])

    with pytest.raises(ValueError, match="Gold reconciliation"):
        task.main()

    assert [audit["quality_status"] for audit in audits] == ["stale"]
