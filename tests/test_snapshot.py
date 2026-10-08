"""Offline App snapshots: what is recorded from the warehouse is replayed identically, without network."""
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/gold_viewer"))
import snapshot  # noqa: E402


class FakeArray(list):
    def tolist(self):
        return list(self)


class FakeCursor:
    def __init__(self, calls): self.calls = calls
    def __enter__(self): return self
    def __exit__(self, *args): return False

    def execute(self, statement, *parameters):
        self.calls.append((statement, parameters))
        self.description = [("company_id",), ("value",), ("observed_at",), ("period_end",), ("categories",)]

    def fetchall(self):
        return [("IFC", Decimal("94.9"), datetime(2026, 10, 7, 18, 28, tzinfo=UTC), date(2026, 6, 30), FakeArray(["Communiqué"]))]


class FakeConnection:
    def __init__(self): self.calls = []
    def cursor(self): return FakeCursor(self.calls)


def read(connection, statement, *parameters):
    with connection.cursor() as cursor:
        cursor.execute(statement, *parameters)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def test_recorded_statements_replay_identically_offline(tmp_path):
    path = tmp_path / "snapshot.json"
    live = FakeConnection()
    recorder = snapshot.RecordingConnection(live, path)
    first = read(recorder, "SELECT company_id, value\n  FROM t WHERE metric_id = ?", ("combined_ratio",))
    second = read(recorder, "SELECT * FROM audit")
    assert live.calls == [("SELECT company_id, value\n  FROM t WHERE metric_id = ?", (("combined_ratio",),)), ("SELECT * FROM audit", ())]
    replay = snapshot.ReplayConnection(path)
    assert read(replay, "SELECT company_id,   value FROM t WHERE metric_id = ?", ("combined_ratio",)) == [
        dict(row, categories=["Communiqué"]) for row in first]  # whitespace does not matter; arrays come back as lists
    assert read(replay, "SELECT * FROM audit") == [dict(row, categories=["Communiqué"]) for row in second]
    with pytest.raises(LookupError, match="not in the offline snapshot"):
        read(replay, "SELECT company_id, value FROM t WHERE metric_id = ?", ("net_income",))  # other parameters


def test_the_deployed_app_never_enables_offline_or_recording():
    app_yaml = (Path(__file__).resolve().parents[1] / "apps/gold_viewer/app.yaml").read_text(encoding="utf-8")
    assert "VIGIE_OFFLINE_SNAPSHOT" not in app_yaml and "VIGIE_RECORD_SNAPSHOT" not in app_yaml
