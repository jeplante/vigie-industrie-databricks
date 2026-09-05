from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import pytest

from vigie_databricks.tasks import finance_publish as task


@dataclass(frozen=True)
class LayerResult:
    reconciliation_delta: int = 0


class FakeTable:
    def collect(self):
        return []


class FakeCatalog:
    @staticmethod
    def tableExists(_name):
        return False


class FakeSpark:
    catalog = FakeCatalog()

    @staticmethod
    def table(_name):
        return FakeTable()


class FakeBuilder:
    @staticmethod
    def getOrCreate():
        return FakeSpark()


class FakeSparkSession:
    builder = FakeBuilder()


def _argv(fixture, config_directory):
    return [
        "finance_publish",
        "--config-directory", str(config_directory),
        "--candidate-fixture-path", str(fixture),
        "--bronze-object", "c.s.bronze",
        "--silver-object", "c.s.silver",
        "--gold-object", "c.s.gold",
        "--audit-object", "c.s.audit",
        "--run-id", "run-1",
    ]


def test_finance_publish_runs_layers_only_after_contract_validation(monkeypatch, tmp_path, capsys):
    fixture = tmp_path / "candidates.json"
    fixture.write_text("[]", encoding="utf-8")
    calls = []
    publication = type("Publication", (), {"quality_status": "current", "observations": ({"observation_id": "o"},), "rejection_reasons": ()})()
    monkeypatch.setattr(task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(task, "load_insurer_contract", lambda _: object())
    monkeypatch.setattr(task, "publish_finance_candidates", lambda *_: publication)
    monkeypatch.setattr(task, "load_bronze_observations", lambda *args: calls.append("bronze") or LayerResult())
    monkeypatch.setattr(task, "load_silver_observations", lambda *args: calls.append("silver") or LayerResult())
    monkeypatch.setattr(task, "load_gold_observations", lambda *args: calls.append("gold") or LayerResult())
    monkeypatch.setattr(task, "upsert_finance_run_audit", lambda *args: calls.append("audit"))
    monkeypatch.setattr(sys, "argv", _argv(fixture, tmp_path))

    task.main()

    assert calls == ["bronze", "silver", "gold", "audit"]
    assert json.loads(capsys.readouterr().out)["quality_status"] == "current"


def test_finance_publish_rejection_preserves_tables_and_records_audit(monkeypatch, tmp_path):
    fixture = tmp_path / "candidates.json"
    fixture.write_text("[]", encoding="utf-8")
    calls = []
    publication = type("Publication", (), {"quality_status": "stale", "observations": (), "rejection_reasons": ("bad candidate",)})()
    monkeypatch.setattr(task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(task, "load_insurer_contract", lambda _: object())
    monkeypatch.setattr(task, "publish_finance_candidates", lambda *_: publication)
    monkeypatch.setattr(task, "load_bronze_observations", lambda *args: calls.append("bronze"))
    monkeypatch.setattr(task, "upsert_finance_run_audit", lambda *args: calls.append("audit"))
    monkeypatch.setattr(sys, "argv", _argv(fixture, tmp_path))

    with pytest.raises(ValueError, match="last-known-good"):
        task.main()

    assert calls == ["audit"]
