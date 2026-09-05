"""Bounded retrieval of approved insurer financial documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from vigie_databricks.finance_documents import FinancialDocument, create_financial_document
from vigie_databricks.insurer_contract import InsurerContract


ALLOWED_DOCUMENT_CONTENT_TYPES = {"application/pdf", "text/html", "application/xhtml+xml"}


def acquire_discovery_page(source, *, timeout_seconds: int = 20, max_response_bytes: int = 2_000_000) -> str:
    """Fetch one approved landing page without following redirects to an unapproved host."""
    if not 1 <= timeout_seconds <= 60 or not 1 <= max_response_bytes <= 5_000_000:
        raise ValueError("invalid discovery page limits")
    request = Request(source.url, headers={"User-Agent": "VigieDatabricks/1.0", "Accept": "text/html"})
    with urlopen(request, timeout=timeout_seconds) as response:
        final_host = urlparse(response.geturl()).hostname
        if final_host not in source.allowed_hosts:
            raise ValueError("Discovery redirect host is not approved")
        if response.headers.get_content_type().lower() not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("Unsupported discovery page content type")
        content = response.read(max_response_bytes + 1)
        if len(content) > max_response_bytes:
            raise ValueError("Discovery page exceeds the configured size limit")
        return content.decode(response.headers.get_content_charset() or "utf-8", errors="replace")


@dataclass(frozen=True)
class FinancialDocumentFetch:
    document: FinancialDocument
    content: bytes | None


def acquire_financial_document(
    contract: InsurerContract,
    company_id: str,
    document_type: str,
    source_url: str,
    *,
    known_content_hash: str | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout_seconds: int = 20,
    max_response_bytes: int = 15_000_000,
) -> FinancialDocumentFetch:
    if not 1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be between 1 and 60")
    if not 1 <= max_response_bytes <= 25_000_000:
        raise ValueError("max_response_bytes must be between 1 and 25000000")
    headers = {"User-Agent": "VigieDatabricks/1.0", "Accept": ", ".join(sorted(ALLOWED_DOCUMENT_CONTENT_TYPES))}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    request = Request(source_url, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type not in ALLOWED_DOCUMENT_CONTENT_TYPES:
                raise ValueError(f"Unsupported financial document content type: {content_type}")
            content = response.read(max_response_bytes + 1)
            if len(content) > max_response_bytes:
                raise ValueError("Financial document exceeds the configured size limit")
            document = create_financial_document(
                contract,
                company_id,
                document_type,
                source_url,
                "fetched",
                content=content,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                content_type=content_type,
            )
            return FinancialDocumentFetch(document, content)
    except HTTPError as error:
        if error.code != 304:
            raise
        document = create_financial_document(
            contract,
            company_id,
            document_type,
            source_url,
            "unchanged",
            known_content_hash=known_content_hash,
            etag=etag,
            last_modified=last_modified,
        )
        return FinancialDocumentFetch(document, None)
