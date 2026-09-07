from vigie_databricks.finance_history import VALIDATED_STATUS, history_basis, validate_historical_candidate


def candidate(**overrides):
    row = {"validation_status": "needs_period_and_accounting_basis_review", "company_id": "MFC", "period_id": "2024-Q2", "source_document_hash": "abc", "source_url": "https://www.manulife.com/q2.pdf"}
    row.update(overrides)
    return row


def document(**overrides):
    row = {"acquisition_status": "fetched", "document_type": "quarterly_report", "company_id": "MFC", "reporting_period": "2024-Q2", "content_hash": "abc", "source_url": "https://www.manulife.com/q2.pdf"}
    row.update(overrides)
    return row


def test_accepts_a_traceable_quarterly_candidate():
    assert validate_historical_candidate(candidate(), document()) == (VALIDATED_STATUS, None)


def test_rejects_annual_and_mismatched_documents():
    assert validate_historical_candidate(candidate(period_id="2024-AN"), document())[1] == "non_quarterly_period"
    assert validate_historical_candidate(candidate(), document(document_type="annual_report"))[1] == "source_document_not_quarterly"
    assert validate_historical_candidate(candidate(), document(content_hash="other"))[1] == "source_content_hash_mismatch"


def test_history_basis_never_sums_ratios_or_assets():
    assert history_basis("core_earnings") == "additive"
    assert history_basis("net_income") == "additive"
    assert history_basis("core_roe") == "point_in_time"
    assert history_basis("assets_under_management") == "point_in_time"
