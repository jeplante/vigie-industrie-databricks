import json
from pathlib import Path
import sys

import pytest

from vigie_databricks.pnc_live import PncAcquisitionResult
from vigie_databricks.tasks import pnc_acquire


ROOT = Path(__file__).resolve().parents[1]


def _run(monkeypatch, capsys, companies):
    monkeypatch.setattr(sys, "argv", [
        "pnc_acquire", "--config-directory", str(ROOT / "config/pnc"),
        "--manifest", str(ROOT / "config/pnc/history/2025-Q2.yaml"),
        "--allow-network",
    ])
    result = PncAcquisitionResult((), tuple({"company_id": company} for company in companies), {})
    monkeypatch.setattr(pnc_acquire, "acquire_pnc_documents", lambda *args, **kwargs: result)


def test_explicitly_unavailable_aviva_does_not_fail_task(monkeypatch, capsys):
    _run(monkeypatch, capsys, ("IFC", "TD", "DFY"))
    pnc_acquire.main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "acquired_needs_review"
    assert payload["sources_without_candidates"] == ["AV"]
    assert payload["explicitly_unavailable_sources"] == ["AV"]


def test_missing_acquirable_td_still_fails_task(monkeypatch, capsys):
    _run(monkeypatch, capsys, ("IFC", "DFY"))
    with pytest.raises(SystemExit, match="1"):
        pnc_acquire.main()
    assert json.loads(capsys.readouterr().out)["status"] == "extraction_incomplete"
