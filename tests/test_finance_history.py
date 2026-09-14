from pathlib import Path

from vigie_databricks.finance_history import VALIDATED_STATUS, anomalous_observations, history_basis, incomplete_periods, select_preferred_documents, validate_historical_candidate
from vigie_databricks.insurer_contract import load_insurer_contract


ROOT = Path(__file__).resolve().parents[1]


def candidate(**overrides):
    row = {"validation_status": "needs_period_and_accounting_basis_review", "observation_id": "MFC-2024-Q2-core_eps", "company_id": "MFC", "period_id": "2024-Q2", "metric_id": "core_eps", "value": 1.0, "unit": "CAD_PER_SHARE", "quality_status": "candidate", "context": "core EPS $1.00", "source_document_hash": "abc", "source_url": "https://www.manulife.com/q2-financial-results.pdf"}
    row.update(overrides)
    return row


def document(**overrides):
    row = {"acquisition_status": "fetched", "document_type": "quarterly_report", "company_id": "MFC", "reporting_period": "2024-Q2", "content_hash": "abc", "source_url": "https://www.manulife.com/q2-financial-results.pdf"}
    row.update(overrides)
    return row


def test_accepts_a_traceable_quarterly_candidate():
    assert validate_historical_candidate(candidate(), document(), load_insurer_contract(ROOT / "config")) == (VALIDATED_STATUS, None)


def test_rejects_annual_and_mismatched_documents():
    assert validate_historical_candidate(candidate(period_id="2024-AN"), document())[1] == "non_quarterly_period"
    assert validate_historical_candidate(candidate(), document(document_type="annual_report"))[1] == "source_document_not_quarterly"
    assert validate_historical_candidate(candidate(), document(content_hash="other"))[1] == "source_content_hash_mismatch"


def test_rejects_disallowed_source_and_context_without_metric_alias():
    assert validate_historical_candidate(candidate(), document(source_url="https://www.manulife.com/q2-transcript.pdf"))[1] == "source_document_disallowed"
    assert validate_historical_candidate(candidate(context="unrelated $1.00"), document())[1] == "metric_context_missing_alias"


def test_reports_missing_expected_metrics_by_company_and_period():
    validated = [{"company_id": "MFC", "period_id": "2024-Q2", "metric_id": "core_eps", "validation_status": VALIDATED_STATUS}]
    assert incomplete_periods(validated)[("MFC", "2024-Q2")] == ("core_earnings", "core_roe", "licat_ratio", "net_income")
    assert incomplete_periods([], [("IAG", "2024-Q1")])[("IAG", "2024-Q1")] == (
        "assets_under_administration", "core_earnings", "core_eps", "core_roe", "licat_ratio", "net_income"
    )


def test_flags_only_extreme_same_quarter_year_over_year_changes():
    rows = [
        {"observation_id": "old", "company_id": "MFC", "metric_id": "core_eps", "period_id": "2023-Q2", "value": 1.0, "validation_status": VALIDATED_STATUS},
        {"observation_id": "normal", "company_id": "MFC", "metric_id": "core_eps", "period_id": "2024-Q2", "value": 1.5, "validation_status": VALIDATED_STATUS},
        {"observation_id": "extreme", "company_id": "MFC", "metric_id": "core_eps", "period_id": "2025-Q2", "value": 4.0, "validation_status": VALIDATED_STATUS},
    ]
    assert anomalous_observations(rows) == {"extreme": "extreme_yoy_change_vs_2024-Q2"}


def test_source_selection_excludes_certificates_and_prefers_shareholder_reports():
    documents = [
        {"company_id": "IAG", "reporting_period": "2025-Q2", "source_url": "https://ia.ca/q2-certification.pdf", "fetched_at": "2026-09-01"},
        {"company_id": "IAG", "reporting_period": "2025-Q2", "source_url": "https://ia.ca/q2-news-release.pdf", "fetched_at": "2026-08-01"},
        {"company_id": "GWO", "reporting_period": "2025-Q2", "source_url": "https://greatwestlifeco.com/q2-earnings-release.pdf", "fetched_at": "2026-09-01"},
        {"company_id": "GWO", "reporting_period": "2025-Q2", "source_url": "https://greatwestlifeco.com/q2-report-to-shareholders.pdf", "fetched_at": "2026-08-01"},
        {"company_id": "IAG", "reporting_period": "2025-Q3", "source_url": "https://ia.ca/q3-news-release-dividend.pdf", "fetched_at": "2026-09-02"},
        {"company_id": "IAG", "reporting_period": "2025-Q3", "source_url": "https://ia.ca/q3-news-release-acc.pdf", "fetched_at": "2026-08-02"},
        {"company_id": "IAG", "reporting_period": "2025-Q4", "source_url": "https://ia.ca/q4-news-release-ncib.pdf", "fetched_at": "2026-09-03"},
        {"company_id": "IAG", "reporting_period": "2025-Q4", "source_url": "https://ia.ca/q4-shareholders-report.pdf", "fetched_at": "2026-08-03"},
    ]
    selected = select_preferred_documents(documents)
    assert selected[("IAG", "2025-Q2")]["source_url"].endswith("news-release.pdf")
    assert selected[("GWO", "2025-Q2")]["source_url"].endswith("report-to-shareholders.pdf")
    assert selected[("IAG", "2025-Q3")]["source_url"].endswith("news-release-acc.pdf")
    assert selected[("IAG", "2025-Q4")]["source_url"].endswith("shareholders-report.pdf")


def test_history_basis_never_sums_ratios_or_assets():
    assert history_basis("core_earnings") == "additive"
    assert history_basis("net_income") == "additive"
    assert history_basis("core_roe") == "point_in_time"
    assert history_basis("assets_under_management") == "point_in_time"
