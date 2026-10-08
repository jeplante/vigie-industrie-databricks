"""Record the App's SQL statements once, then replay them without Databricks.

Testing the App against the live SQL warehouse keeps the warehouse running (10-minute auto-stop after each
statement) and spent most of the compute quota on 2026-10-07. ``RecordingConnection`` wraps the real
connection during one session and writes every statement with its result to a JSON file;
``ReplayConnection`` answers the same statements from that file, offline. A statement that was not
recorded raises, so a missing case is visible instead of silently empty.

Set ``VIGIE_RECORD_SNAPSHOT=<file>`` to record and ``VIGIE_OFFLINE_SNAPSHOT=<file>`` to replay (see
``scripts/run_app_offline.py``). Neither is ever set in the deployed App.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Sequence


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if hasattr(value, "tolist"):  # numpy arrays for ARRAY columns
        return [_encode(item) for item in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if "__datetime__" in value:
            return datetime.fromisoformat(value["__datetime__"])
        if "__date__" in value:
            return date.fromisoformat(value["__date__"])
        if "__decimal__" in value:
            return Decimal(value["__decimal__"])
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def statement_key(statement: str, parameters: Sequence[Any] = ()) -> str:
    """Whitespace-insensitive key of a statement and its parameters."""
    return json.dumps([" ".join(str(statement).split()), [_encode(item) for item in (parameters or ())]], sort_keys=True, default=str)


class _RecordingCursor:
    def __init__(self, owner: "RecordingConnection"):
        self.owner, self.cursor = owner, owner.connection.cursor()

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, statement, *parameters):
        # forward exactly what the caller passed: some readers give parameters, others none
        self.key = statement_key(statement, parameters[0] if parameters else ())
        return self.cursor.execute(statement, *parameters)

    @property
    def description(self):
        return self.cursor.description

    def fetchall(self):
        rows = self.cursor.fetchall()
        columns = [column[0] for column in self.cursor.description or ()]
        self.owner.record(self.key, columns, rows)
        return rows


class RecordingConnection:
    """Pass-through connection that saves every statement's result to ``path`` as it is read."""

    def __init__(self, connection: Any, path: str | Path):
        self.connection, self.path = connection, Path(path)
        self.entries: dict[str, dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def cursor(self):
        return _RecordingCursor(self)

    def record(self, key: str, columns: list[str], rows: Sequence[Sequence[Any]]) -> None:
        self.entries[key] = {"columns": columns, "rows": [[_encode(value) for value in row] for row in rows]}
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=0), encoding="utf-8")


class _ReplayCursor:
    def __init__(self, entries: dict[str, dict[str, Any]]):
        self.entries, self.entry = entries, None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=()):
        key = statement_key(statement, parameters)
        if key not in self.entries:
            raise LookupError("statement not in the offline snapshot; record it once with VIGIE_RECORD_SNAPSHOT: "
                              + " ".join(str(statement).split())[:160])
        self.entry = self.entries[key]

    @property
    def description(self):
        return [(column,) for column in self.entry["columns"]] if self.entry else None

    def fetchall(self):
        return [tuple(_decode(value) for value in row) for row in self.entry["rows"]]


class ReplayConnection:
    """Connection that answers recorded statements from a snapshot file, without any network access."""

    def __init__(self, path: str | Path):
        self.entries = json.loads(Path(path).read_text(encoding="utf-8"))

    def cursor(self):
        return _ReplayCursor(self.entries)
