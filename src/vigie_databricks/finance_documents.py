"""Finance document and run-audit contracts for insurer source acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from urllib.parse import urlparse

from vigie_databricks.insurer_contract import FinancialSource, InsurerContract


FINANCIAL_DOCUMENT_SCHEMA = (
    "document_id string,company_id string,source_id string,document_type string,"
    "source_url string,content_hash string,etag string,last_modified string,"
    "content_type string,content_length long,raw_content_path string,reporting_period string,published_at timestamp,fetched_at timestamp,"
    "acquisition_status string,error_code string"
)
FINANCE_RUN_AUDIT_SCHEMA = (
    "run_id string,observed_at timestamp,source_mode string,sources_succeeded long,"
    "sources_failed long,documents_discovered long,documents_fetched long,"
    "documents_unchanged long,candidate_observations long,ai_model_calls long,retention_deleted_files long,quality_status string"
)
VALID_ACQUISITION_STATUSES = {"discovered", "fetched", "unchanged", "failed"}


@dataclass(frozen=True)
class FinancialDocument:
    document_id: str
    company_id: str
    source_id: str
    document_type: str
    source_url: str
    content_hash: str
    etag: str | None
    last_modified: str | None
    content_type: str | None
    content_length: int | None
    raw_content_path: str | None
    reporting_period: str | None
    published_at: datetime | None
    fetched_at: datetime
    acquisition_status: str
    error_code: str | None


def document_id(company_id: str, document_type: str, source_url: str) -> str:
    material = f"{company_id}||{document_type}||{source_url.strip()}"
    return hashlib.sha256(material.encode()).hexdigest()


def create_financial_document(
    contract: InsurerContract,
    company_id: str,
    document_type: str,
    source_url: str,
    acquisition_status: str,
    *,
    content: bytes | None = None,
    known_content_hash: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    content_type: str | None = None,
    raw_content_path: str | None = None,
    reporting_period: str | None = None,
    published_at: datetime | None = None,
    error_code: str | None = None,
    fetched_at: datetime | None = None,
) -> FinancialDocument:
    source = _source_for(contract, company_id)
    if document_type not in source.document_types:
        raise ValueError("document_type is not configured for the company source")
    _validate_source_url(source, source_url)
    if acquisition_status not in VALID_ACQUISITION_STATUSES:
        raise ValueError("acquisition_status is unsupported")
    if acquisition_status == "fetched" and content is None:
        raise ValueError("fetched documents require content")
    if acquisition_status == "unchanged" and not known_content_hash:
        raise ValueError("unchanged documents require known_content_hash")
    if acquisition_status == "failed" and not error_code:
        raise ValueError("failed documents require error_code")
    if acquisition_status != "failed" and error_code:
        raise ValueError("only failed documents may have error_code")
    content_hash = hashlib.sha256(content).hexdigest() if content is not None else known_content_hash or ""
    return FinancialDocument(
        document_id(company_id, document_type, source_url),
        company_id,
        source.source_id,
        document_type,
        source_url,
        content_hash,
        etag,
        last_modified,
        content_type,
        len(content) if content is not None else None,
        raw_content_path,
        reporting_period,
        published_at,
        fetched_at or datetime.now(UTC),
        acquisition_status,
        error_code,
    )


def _source_for(contract: InsurerContract, company_id: str) -> FinancialSource:
    try:
        return contract.financial_sources[company_id]
    except KeyError as error:
        raise ValueError("company_id is not configured") from error


def _validate_source_url(source: FinancialSource, source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source_url must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError("source_url must not include credentials or a non-standard port")
    if parsed.hostname not in source.allowed_hosts:
        raise ValueError("source_url host is not approved for the company")
