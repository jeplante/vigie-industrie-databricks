"""Bounded live Finance acquisition and deterministic candidate construction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any, Callable

from vigie_databricks.finance_acquisition import acquire_discovery_page, acquire_financial_document
from vigie_databricks.finance_discovery import DiscoveredFinancialDocument, discover_financial_documents
from vigie_databricks.finance_documents import FinancialDocument, create_financial_document
from vigie_databricks.finance_extraction import extract_document_text, extract_finance_metrics, infer_reporting_period
from vigie_databricks.insurer_contract import InsurerContract


@dataclass(frozen=True)
class LiveFinanceResult:
    documents: tuple[FinancialDocument, ...]
    candidates: tuple[dict[str, Any], ...]
    sources_succeeded: int
    source_errors: dict[str, str]
    documents_discovered: int
    documents_fetched: int
    documents_unchanged: int


def _latest_document(documents):
    ranked = []
    for document in documents:
        period = infer_reporting_period(f"{document.title} {document.source_url}")
        if period:
            ranked.append((period, document.source_url, document))
    return max(ranked, default=(None, None, None))[2]


def discover_mfc_direct_documents(now: datetime | None = None, *, max_quarters: int = 6) -> list[DiscoveredFinancialDocument]:
    """Build a bounded list of official MFC shareholder-report candidates."""
    if not 1 <= max_quarters <= 8:
        raise ValueError("max_quarters must be between 1 and 8")
    current = now or datetime.now(UTC)
    year, quarter = current.year, (current.month - 1) // 3 + 1
    documents = []
    for _ in range(max_quarters):
        documents.append(DiscoveredFinancialDocument(
            "quarterly_report",
            f"https://www.manulife.com/content/dam/manulife-com/ca/financial-documents/investors/MFC_SR_{year}_Q{quarter}_EN.pdf",
            f"MFC Q{quarter} {year} report to shareholders",
        ))
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    return documents


def _safe_error(error: Exception) -> str:
    material = f"{type(error).__name__}_{error}"
    value = re.sub(r"[^a-z0-9]+", "_", material.lower()).strip("_")
    return (value or "source_error")[:80]


def _raw_path(volume: str, document: FinancialDocument) -> Path:
    extension = ".pdf" if document.content_type == "application/pdf" else ".html"
    root = Path(volume)
    target = root / document.company_id / f"{document.content_hash}{extension}"
    if root not in target.parents:
        raise ValueError("raw content path escaped configured volume")
    return target


def persist_raw_content(volume: str, document: FinancialDocument, content: bytes) -> FinancialDocument:
    target = _raw_path(volume, document)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
    return replace(document, raw_content_path=str(target).replace("\\", "/"))


def acquire_live_finance(
    contract: InsurerContract,
    prior_by_url: dict[str, dict[str, Any]],
    *,
    persist_raw: bool,
    page_fetcher: Callable = acquire_discovery_page,
    document_fetcher: Callable = acquire_financial_document,
    ai_fallback: Callable[[str, str, str, str, str], list[dict[str, Any]]] | None = None,
) -> LiveFinanceResult:
    documents: list[FinancialDocument] = []
    candidates: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    discovered_count = fetched_count = unchanged_count = succeeded = 0
    for company_id in sorted(contract.financial_sources):
        source = contract.financial_sources[company_id]
        try:
            discovered = (
                discover_mfc_direct_documents()
                if company_id == "MFC"
                else discover_financial_documents(page_fetcher(source), source)
            )
            discovered_count += len(discovered)
            selected_documents = discovered if company_id == "MFC" else [_latest_document(discovered)]
            selected_documents = [item for item in selected_documents if item is not None]
            if not selected_documents:
                raise ValueError("no_report_with_explicit_period")
            fetched = None; selected = None; prior = {}
            for candidate_document in selected_documents:
                candidate_prior = prior_by_url.get(candidate_document.source_url, {})
                try:
                    fetched = document_fetcher(
                        contract, company_id, candidate_document.document_type, candidate_document.source_url,
                        known_content_hash=candidate_prior.get("content_hash"), etag=candidate_prior.get("etag"),
                        last_modified=candidate_prior.get("last_modified"),
                    )
                    selected, prior = candidate_document, candidate_prior
                    break
                except Exception:
                    if company_id != "MFC":
                        raise
            if fetched is None or selected is None:
                raise ValueError("no_accessible_official_report")
            period_id = infer_reporting_period(f"{selected.title} {selected.source_url}")
            document = replace(fetched.document, reporting_period=period_id)
            if fetched.content is None:
                unchanged_count += 1
                raw_path = prior.get("raw_content_path")
                if not raw_path or not Path(raw_path).exists():
                    raise ValueError("unchanged_document_raw_content_missing")
                content = Path(raw_path).read_bytes()
                document = replace(document, raw_content_path=raw_path)
            else:
                fetched_count += 1
                content = fetched.content
                if persist_raw:
                    document = persist_raw_content(contract.finance_policy.raw_content_volume, document, content)
            text = extract_document_text(content, document.content_type or "application/pdf")
            metrics = extract_finance_metrics(company_id, text, contract)
            ai_candidates = [] if metrics or ai_fallback is None else ai_fallback(company_id, period_id, selected.source_url, document.content_hash, text)
            if not metrics and not ai_candidates:
                raise ValueError("deterministic_extraction_empty")
            for metric in metrics:
                candidates.append({
                    "observation_id": f"{company_id}-{period_id}-{metric.metric_id}",
                    "company_id": company_id, "metric_id": metric.metric_id,
                    "period_id": period_id, "value": metric.value, "unit": metric.unit,
                    "source_url": selected.source_url,
                    "source_document_hash": document.content_hash, "quality_status": "candidate",
                })
            candidates.extend(ai_candidates)
            documents.append(document)
            succeeded += 1
        except Exception as error:
            errors[company_id] = _safe_error(error)
            documents.append(create_financial_document(
                contract, company_id, source.document_types[0], source.url, "failed",
                error_code=errors[company_id],
            ))
    return LiveFinanceResult(tuple(documents), tuple(candidates), succeeded, errors, discovered_count, fetched_count, unchanged_count)
