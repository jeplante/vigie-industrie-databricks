"""Bounded P&C document acquisition; extracted values remain review candidates."""

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import re

from vigie_databricks.finance_acquisition import acquire_financial_document
from vigie_databricks.finance_documents import _validate_source_url
from vigie_databricks.finance_extraction import extract_document_text
from vigie_databricks.finance_live import persist_raw_content
from vigie_databricks.pnc_extraction import extract_pnc_metrics
from vigie_databricks.pnc_history import PNC_REVIEW_STATUS


@dataclass(frozen=True)
class PncAcquisitionResult:
    documents: tuple
    candidates: tuple
    errors: dict


def acquire_pnc_documents(contract, manifest, prior_by_url=None, *, persist_raw=False,
                          document_fetcher=acquire_financial_document,
                          text_extractor=None):
    """Acquire at most one explicit document per configured issuer.

    Manifest periods are discovery hints, not proof of a quarterly accounting
    basis. This function does not validate or publish financial observations.
    """
    entries = list(manifest)
    companies = [entry.get("company_id") for entry in entries]
    if len(companies) != len(set(companies)) or set(companies) != set(contract.companies):
        raise ValueError("manifest must contain exactly one document per P&C issuer")
    for entry in entries:
        source = contract.financial_sources[entry["company_id"]]
        if not re.fullmatch(r"20\d{2}-Q[1-4]", str(entry.get("period_id", ""))):
            raise ValueError("manifest requires a quarterly discovery period")
        if entry.get("unavailable_reason"):
            if entry["unavailable_reason"] != "no_quarterly_segment_disclosure":
                raise ValueError("unsupported unavailable reason")
            if entry.get("source_url") or entry.get("document_type"):
                raise ValueError("unavailable source cannot have an acquisition URL or document type")
            _validate_source_url(source, entry["reference_url"])
            continue
        _validate_source_url(source, entry["source_url"])
        if entry.get("document_type") not in source.document_types:
            raise ValueError("unsupported document type")
    prior_by_url = prior_by_url or {}
    documents, candidates, errors = [], [], {}
    for entry in entries:
        if entry.get("unavailable_reason"):
            continue
        company, url = entry["company_id"], entry["source_url"]
        try:
            prior = prior_by_url.get(url, {})
            fetched = document_fetcher(
                contract, company, entry["document_type"], url,
                known_content_hash=prior.get("content_hash"), etag=prior.get("etag"),
                last_modified=prior.get("last_modified"),
            )
            document = replace(fetched.document, reporting_period=entry["period_id"])
            content = fetched.content
            if content is None:
                root = Path(contract.finance_policy.raw_content_volume).resolve()
                raw = Path(prior.get("raw_content_path") or "").resolve()
                if root not in raw.parents or not raw.is_file():
                    raise ValueError("cached_document_unavailable")
                if raw.stat().st_size > 25_000_000:
                    raise ValueError("cached_document_too_large")
                content = raw.read_bytes()
                document = replace(document, raw_content_path=str(raw), content_type=prior.get("content_type"))
            if hashlib.sha256(content).hexdigest() != document.content_hash:
                raise ValueError("document_hash_mismatch")
            if persist_raw:
                document = persist_raw_content(contract.finance_policy.raw_content_volume, document, content)
            documents.append(document)
            content_type = document.content_type or "application/pdf"
            if text_extractor is None:
                # TD's PDF glyph layout splits words and even numbers in plain
                # mode; layout mode preserves the standalone Insurance line.
                text = extract_document_text(
                    content, content_type,
                    pdf_extraction_mode="layout" if company == "TD" and content_type == "application/pdf" else "plain",
                )
            else:
                text = text_extractor(content, content_type)
            for metric in extract_pnc_metrics(company, text, contract):
                candidates.append({
                    "observation_id": f"{company}-{entry['period_id']}-{metric.metric_id}",
                    "company_id": company, "period_id": entry["period_id"],
                    "metric_id": metric.metric_id, "value": metric.value, "unit": metric.unit,
                    "source_url": url, "source_document_hash": document.content_hash,
                    "context": metric.context, "quality_status": "candidate",
                    "validation_status": PNC_REVIEW_STATUS,
                })
        except Exception as error:
            # Keep exceptions bounded and avoid leaking response bodies or credentials.
            errors[company] = type(error).__name__
    return PncAcquisitionResult(tuple(documents), tuple(candidates), errors)
