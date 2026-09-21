"""Pure P&C batch publication decision; storage is performed by the caller."""

from vigie_databricks.finance_publication import FinancePublicationResult
from vigie_databricks.insurer_contract import InsurerContract
from vigie_databricks.pnc_history import PNC_VALIDATED_STATUS, validate_pnc_candidate


def publish_pnc_candidates(candidates, documents, prior_published, contract: InsurerContract):
    """Revalidate the entire batch and preserve last-known-good on any failure.

    Document lookup includes content hash so a changed URL cannot accidentally
    validate a candidate extracted from a different revision. Valid batches
    merge by observation ID, retaining historical observations.
    """
    if not candidates:
        return FinancePublicationResult(tuple(prior_published), "stale", ("candidate_batch_empty",))
    index = {}
    reasons = set()
    for document in documents:
        key = (document.get("company_id"), document.get("source_url"), document.get("content_hash"))
        if key in index and index[key] != document:
            reasons.add("conflicting_source_documents")
        index[key] = document
    identifiers = set()
    accepted = []
    for candidate in candidates:
        identifier = candidate.get("observation_id")
        if identifier in identifiers:
            reasons.add("duplicate_observation_id")
        identifiers.add(identifier)
        key = (candidate.get("company_id"), candidate.get("source_url"), candidate.get("source_document_hash"))
        status, reason = validate_pnc_candidate(candidate, index.get(key), contract)
        if status != PNC_VALIDATED_STATUS:
            reasons.add(reason)
        else:
            accepted.append({**candidate, "validation_status": status})
    if reasons:
        return FinancePublicationResult(tuple(prior_published), "stale", tuple(sorted(reasons)))
    merged = {row["observation_id"]: row for row in prior_published}
    merged.update({row["observation_id"]: row for row in accepted})
    return FinancePublicationResult(tuple(merged[key] for key in sorted(merged)), "current", ())
