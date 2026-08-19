from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import pytest

from vigie_databricks.tasks import bronze as bronze_task
from vigie_databricks.tasks import gold as gold_task
from vigie_databricks.tasks import silver as silver_task


@dataclass(frozen=True)
class FakeResult:
    layer: str
    rows: int


class FakeSparkSession:
    builder = None


class FakeBuilder:
    @staticmethod
    def getOrCreate() -> FakeSparkSession:
        return FakeSparkSession()


FakeSparkSession.builder = FakeBuilder()


def test_bronze_entrypoint_resolves_fixture_and_delegates(monkeypatch, tmp_path, capsys) -> None:
    fixture = tmp_path / "rows.json"
    rows = [{"observation_id": "o1", "company_id": "c1"}]
    fixture.write_text(json.dumps(rows), encoding="utf-8")
    calls = []

    def fake_load(**kwargs):
        calls.append(kwargs)
        return FakeResult("bronze", 1)

    monkeypatch.setattr(bronze_task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(bronze_task, "load_bronze_observations", fake_load)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bronze",
            "--catalog",
            "c",
            "--schema",
            "s",
            "--bronze-object",
            "c.s.bronze",
            "--input-mode",
            "fixture",
            "--input-fixture-path",
            str(fixture),
        ],
    )

    bronze_task.main()

    assert calls[0]["rows"] == rows
    assert calls[0]["bronze_object"] == "c.s.bronze"
    assert json.loads(capsys.readouterr().out)["layer"] == "bronze"


def test_silver_entrypoint_delegates(monkeypatch, capsys) -> None:
    calls = []

    def fake_load(**kwargs):
        calls.append(kwargs)
        return FakeResult("silver", 2)

    monkeypatch.setattr(silver_task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(silver_task, "load_silver_observations", fake_load)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "silver",
            "--catalog",
            "c",
            "--schema",
            "s",
            "--bronze-object",
            "c.s.bronze",
            "--silver-object",
            "c.s.silver",
        ],
    )

    silver_task.main()

    assert calls[0]["bronze_object"] == "c.s.bronze"
    assert calls[0]["silver_object"] == "c.s.silver"
    assert json.loads(capsys.readouterr().out)["metrics"]["rows"] == 2


def test_gold_entrypoint_delegates_and_propagates_failure(monkeypatch) -> None:
    def fail(**kwargs):
        raise RuntimeError("gold failed")

    monkeypatch.setattr(gold_task, "SparkSession", FakeSparkSession)
    monkeypatch.setattr(gold_task, "load_gold_observations", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gold",
            "--catalog",
            "c",
            "--schema",
            "s",
            "--silver-object",
            "c.s.silver",
            "--gold-object",
            "c.s.gold",
        ],
    )

    with pytest.raises(RuntimeError, match="gold failed"):
        gold_task.main()
