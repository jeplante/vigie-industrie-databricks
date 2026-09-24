from pathlib import Path

import pytest
import yaml

from scripts import submit_pnc_history


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "pnc" / "history" / "2026-Q1.yaml"


def test_checked_history_manifest_is_period_bound_and_allowlisted():
    assert submit_pnc_history.checked_manifest(MANIFEST) == MANIFEST.resolve()
    with pytest.raises(ValueError, match="versioned quarter"):
        submit_pnc_history.checked_manifest(ROOT / "tests" / "fixtures" / "pnc_source_manifest.yaml")


def test_history_submit_rejects_off_host_source(tmp_path, monkeypatch):
    monkeypatch.setattr(submit_pnc_history, "HISTORY", tmp_path.resolve())
    entries = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entries["sources"][0]["source_url"] = "https://example.org/ifc.pdf"
    candidate = tmp_path / "2026-Q1.yaml"
    candidate.write_text(yaml.safe_dump(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="not approved"):
        submit_pnc_history.checked_manifest(candidate)


def test_history_submit_rejects_duplicate_issuer(tmp_path, monkeypatch):
    monkeypatch.setattr(submit_pnc_history, "HISTORY", tmp_path.resolve())
    entries = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entries["sources"][1]["company_id"] = "IFC"
    candidate = tmp_path / "2026-Q1.yaml"
    candidate.write_text(yaml.safe_dump(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="one source per insurer"):
        submit_pnc_history.checked_manifest(candidate)
