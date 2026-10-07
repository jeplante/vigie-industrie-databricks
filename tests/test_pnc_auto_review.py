"""Automatic P&C review and report discovery, replacing the hand-written evidence record."""
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from vigie_databricks.insurer_contract import load_insurer_contract
from vigie_databricks.pnc_auto_review import period_end, review_automatically
from vigie_databricks.pnc_discovery import discover_manifest, next_period
from vigie_databricks.pnc_live import acquire_pnc_documents
from vigie_databricks.pnc_publication import gold_rows, publish_pnc_candidates

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_insurer_contract(ROOT / "config/pnc")
TD_URL = "https://www.td.com/content/dam/tdcom/canada/about-td/pdf/quarterly-results/2026/q3/2026-q3-report-shareholders-en.pdf"
DIGEST = "6df473f21b580a745119c5deee17b6c41a681c7b37967eac6dd65f6fe473b9c9"
DFY_URL = "https://www.definityfinancial.com/English/newsroom/news-releases/news-details/2026/Definity-Reports-Third-Quarter-2026-Results/default.aspx"


def candidate(company="TD", metric="net_income", period="2026-Q3", value=0.188, unit="CAD_BILLION",
              context="Quarterly comparison Q3 2026 Insurance net income of $188 million", url=TD_URL, digest=DIGEST):
    return {"observation_id": f"{company}-{period}-{metric}", "company_id": company, "period_id": period,
            "metric_id": metric, "value": value, "unit": unit, "source_url": url, "source_document_hash": digest,
            "context": context, "quality_status": "candidate", "validation_status": "needs_period_and_accounting_basis_review"}


def published(company, metric, period, value):
    return {"observation_id": f"{company}-{period}-{metric}", "company_id": company, "metric_id": metric,
            "period_id": period, "value": value}


TD_HISTORY = [published("TD", "net_income", "2025-Q3", 0.182), published("TD", "net_income", "2026-Q2", 0.279)]


def decisions_of(candidates, history=()):
    return {d["observation_id"]: (d["decision"], d["reason"]) for d in review_automatically(candidates, list(history))[1]}


def test_period_end_follows_each_issuer_calendar():
    assert period_end("2026-Q3", 10) == date(2026, 7, 31)  # TD fiscal Q3
    assert period_end("2026-Q1", 10) == date(2026, 1, 31)
    assert period_end("2025-Q4", 10) == date(2025, 10, 31)
    assert period_end("2026-Q2") == date(2026, 6, 30) and period_end("2025-Q4") == date(2025, 12, 31)
    assert next_period("2026-Q4") == "2027-Q1" and next_period("2026-Q2") == "2026-Q3"


def test_an_accepted_candidate_passes_the_unchanged_publication_gate():
    accepted, decisions = review_automatically([candidate()], TD_HISTORY)
    assert [d["decision"] for d in decisions] == ["accepted"]
    evidence = accepted[0]["basis_evidence"]
    assert evidence["period_end"] == "2026-07-31" and evidence["calendar_basis"] == "fiscal"
    assert evidence["disclosure_scope"] == "insurance_segment" and evidence["reviewed_by"] == "automatic-checks-v1"
    document = {"company_id": "TD", "source_url": TD_URL, "content_hash": DIGEST, "acquisition_status": "fetched",
                "document_type": "quarterly_report", "reporting_period": "2026-Q3"}
    gate = publish_pnc_candidates(accepted, [document], [], CONTRACT)
    assert gate.quality_status == "current", gate.rejection_reasons
    row = gold_rows(gate.observations)[0]
    assert row["validation_status"] == "validated_quarterly" and row["period_end"] == "2026-07-31" and row["value"] == 0.188


def test_metrics_never_published_are_excluded_and_republished_values_are_unchanged():
    roe = candidate("DFY", "operating_roe", "2026-Q2", 12.5, "PERCENT", "operating ROE of 12.5%", DFY_URL)
    ifc_claims = candidate("IFC", "claims_ratio", "2023-Q4", 52.5, "PERCENT", "Claims ratio 52.5 %", DFY_URL)
    again = candidate(period="2026-Q2", value=0.279, context="Quarterly comparison Q2 2026 Insurance net income of $279 million")
    assert decisions_of([roe, ifc_claims, again], TD_HISTORY) == {
        "DFY-2026-Q2-operating_roe": ("excluded", "metric_not_published_for_issuer"),
        "IFC-2023-Q4-claims_ratio": ("excluded", "metric_not_published_for_issuer"),
        "TD-2026-Q2-net_income": ("unchanged", None)}
    revised = dict(again, value=0.3)
    assert decisions_of([revised], TD_HISTORY)["TD-2026-Q2-net_income"][0] == "rejected"  # a restatement needs a look


def test_extraction_errors_seen_in_2023_are_rejected():
    ratio = candidate("IFC", "combined_ratio", "2023-Q2", 2.0, "PERCENT", "Consolidated Highlights Q2-2023 Combined ratio (undiscounted) 2%")
    income = candidate("IFC", "operating_income", "2023-Q2", 0.002, "CAD_BILLION", "Consolidated Highlights Q2-2023 Net operating income 2")
    history = [published("IFC", "operating_income", "2022-Q2", 0.581), published("IFC", "operating_income", "2023-Q1", 0.537)]
    result = decisions_of([ratio, income], history)
    assert result["IFC-2023-Q2-combined_ratio"][1].startswith("ratio_out_of_bounds")
    assert result["IFC-2023-Q2-operating_income"][1].startswith("amount_inconsistent_with_history")


def test_a_catastrophe_quarter_close_to_last_year_is_accepted():
    cat = candidate("DFY", "operating_income", "2024-Q3", 0.0146, "CAD_BILLION", "Operating net income was $14.6 million", DFY_URL)
    history = [published("DFY", "operating_income", "2023-Q3", 0.0176), published("DFY", "operating_income", "2024-Q2", 0.1091)]
    assert decisions_of([cat], history)["DFY-2024-Q3-operating_income"] == ("accepted", None)


def test_period_and_identity_checks():
    no_label = candidate(context="Insurance net income of $188 million")
    cumulative = candidate(context="Insurance net income for the nine months ended July 31, 2026 of $650 million")
    other_quarter = candidate(context="Quarterly comparison Q2 2026 Insurance net income of $188 million")
    for row, reason in ((no_label, "quarter_label_missing_from_context"), (cumulative, "cumulative_period_in_context"),
                        (other_quarter, "context_names_another_quarter")):
        assert decisions_of([row], TD_HISTORY)["TD-2026-Q3-net_income"][1].startswith(reason)
    ratios = [candidate("DFY", metric, "2026-Q3", value, "PERCENT", f"{metric} {value}%", DFY_URL)
              for metric, value in (("combined_ratio", 93.9), ("claims_ratio", 64.2), ("expense_ratio", 33.7))]
    assert {decision[0] for decision in decisions_of(ratios).values()} == {"rejected"}  # 64.2 + 33.7 is not 93.9
    ratios[2]["value"] = 29.7
    assert {decision[0] for decision in decisions_of(ratios).values()} == {"accepted"}


def test_discovery_finds_new_reports_and_declares_the_others():
    gold = [published("IFC", "net_income", "2026-Q2", 0.72), published("DFY", "net_income", "2026-Q2", 0.15),
            published("TD", "net_income", "2026-Q3", 0.188)]
    news = [{"company_id": "DFY", "title": "Definity Financial Corporation Reports Third Quarter 2026 Results", "source_url": DFY_URL},
            {"company_id": "DFY", "title": "Definity to announce third quarter 2026 results on November 5", "source_url": "https://x"},
            {"company_id": "IFC", "title": "Intact Financial Corporation announces third quarter catastrophe loss estimate", "source_url": "https://y"}]
    pages = {company: source.url for company, source in CONTRACT.financial_sources.items()}
    probed = []
    entries, new = discover_manifest(gold, news, pages, now=datetime(2026, 11, 6, tzinfo=UTC), probe=lambda url: probed.append(url) or False)
    by_company = {entry["company_id"]: entry for entry in entries}
    assert new == ["DFY"] and by_company["DFY"]["source_url"] == DFY_URL and by_company["DFY"]["period_id"] == "2026-Q3"
    assert by_company["IFC"]["unavailable_reason"] == "not_yet_published" and by_company["IFC"]["period_id"] == "2026-Q3"
    assert by_company["TD"]["unavailable_reason"] == "not_yet_published"  # fiscal Q4 closed Oct 31; its report answers 404
    assert probed == [TD_URL.replace("q3/2026-q3", "q4/2026-q4")]
    early, _ = discover_manifest(gold, [], pages, now=datetime(2026, 10, 20, tzinfo=UTC), probe=lambda url: probed.append(url) or True)
    assert len(probed) == 1  # before the quarter closes, the address is not even probed
    assert by_company["AV"]["unavailable_reason"] == "no_quarterly_segment_disclosure"
    # the generated manifest is valid for the acquisition (fetch failures are recorded, not raised)
    result = acquire_pnc_documents(CONTRACT, entries, document_fetcher=lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert result.errors == {"DFY": "OSError"}
    later, new = discover_manifest(gold, [], pages, now=datetime(2026, 12, 2, tzinfo=UTC), probe=lambda url: "2026/q4" in url)
    assert new == ["TD"] and next(e for e in later if e["company_id"] == "TD")["source_url"].endswith("2026-q4-report-shareholders-en.pdf")
    assert discover_manifest(gold, [], pages, now=datetime(2026, 12, 2, tzinfo=UTC), probe=lambda url: False)[1] == []
    hosts = {company: source.allowed_hosts for company, source in CONTRACT.financial_sources.items()}
    foreign = [dict(news[0], source_url="https://evil.example.org/release")]
    assert discover_manifest(gold, foreign, pages, now=datetime(2026, 11, 6, tzinfo=UTC), probe=lambda url: False, allowed_hosts=hosts)[1] == []
    assert discover_manifest(gold, news, pages, now=datetime(2026, 11, 6, tzinfo=UTC), probe=lambda url: False, allowed_hosts=hosts)[1] == ["DFY"]


def test_task_auto_publish_publishes_accepted_rows_and_reports_rejections(monkeypatch):
    from vigie_databricks import pnc_storage
    from vigie_databricks.tasks import pnc_acquire

    stored = []
    monkeypatch.setattr(pnc_storage, "publish_pnc_gold", lambda spark, namespace, rows: stored.extend(rows) or len(rows))
    history = [SimpleNamespace(asDict=lambda row=row: row) for row in TD_HISTORY]
    spark = SimpleNamespace(table=lambda name: SimpleNamespace(collect=lambda: history))
    document = SimpleNamespace(company_id="TD", source_url=TD_URL, content_hash=DIGEST, acquisition_status="fetched",
                               document_type="quarterly_report", reporting_period="2026-Q3")
    monkeypatch.setattr(pnc_acquire, "asdict", lambda item: vars(item))
    bad = candidate("DFY", "combined_ratio", "2026-Q3", 2.0, "PERCENT", "Combined ratio 2%", DFY_URL)
    result = SimpleNamespace(candidates=(candidate(), bad), documents=(document,))
    outcome = pnc_acquire._auto_publish(spark, "workspace.vigie", result, CONTRACT)
    assert outcome["published"] == 1 and [row["observation_id"] for row in stored] == ["TD-2026-Q3-net_income"]
    assert [d["observation_id"] for d in outcome["rejected"]] == ["DFY-2026-Q3-combined_ratio"]


def test_the_task_needs_exactly_one_manifest_source(monkeypatch):
    import sys
    from vigie_databricks.tasks import pnc_acquire

    monkeypatch.setattr(sys, "argv", ["pnc_acquire", "--config-directory", str(ROOT / "config/pnc"), "--allow-network"])
    with pytest.raises(SystemExit):
        pnc_acquire.main()


def test_review_without_writing_reports_decisions_but_stores_nothing(monkeypatch):
    from vigie_databricks import pnc_storage
    from vigie_databricks.tasks import pnc_acquire

    monkeypatch.setattr(pnc_storage, "publish_pnc_gold", lambda *a: pytest.fail("dry run must not write"))
    history = [SimpleNamespace(asDict=lambda row=row: row) for row in TD_HISTORY]
    spark = SimpleNamespace(table=lambda name: SimpleNamespace(collect=lambda: history))
    document = SimpleNamespace(company_id="TD", source_url=TD_URL, content_hash=DIGEST, acquisition_status="fetched",
                               document_type="quarterly_report", reporting_period="2026-Q3")
    monkeypatch.setattr(pnc_acquire, "asdict", lambda item: vars(item))
    outcome = pnc_acquire._auto_publish(spark, "workspace.vigie", SimpleNamespace(candidates=(candidate(),), documents=(document,)),
                                        CONTRACT, write=False)
    assert outcome["published"] == 0 and [d["decision"] for d in outcome["decisions"]] == ["accepted"]
