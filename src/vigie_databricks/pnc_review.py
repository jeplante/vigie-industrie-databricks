"""Build an explicit review queue without approving extraction candidates."""

from collections import defaultdict
import math

from vigie_databricks.pnc_history import validate_pnc_candidate, PNC_VALIDATED_STATUS


def attach_reviewed_evidence(candidates, reviews):
    """Attach recorded reviews only to the exact revision, metric and value."""
    result = []
    for candidate in candidates:
        row = dict(candidate)
        matches = [review for review in reviews if all(
            review.get(key) == row.get(key)
            for key in ("company_id", "period_id", "source_document_hash")
        ) and row.get("metric_id") in review.get("metrics", {})]
        if len(matches) > 1:
            raise ValueError("Duplicate review for candidate revision")
        if matches:
            review = matches[0]
            metric = review["metrics"][row["metric_id"]]
            if metric["unit"] == row.get("unit") and math.isclose(
                metric["value"], row["value"], rel_tol=0, abs_tol=1e-12
            ):
                evidence = {key: value.isoformat() if hasattr(value, "isoformat") else value
                            for key, value in review.items() if key not in {"metrics", "exclusions"}}
                evidence.update(metric_id=row["metric_id"], value=row["value"], unit=row["unit"])
                row["basis_evidence"] = evidence
        result.append(row)
    return result


def review_pnc_candidates(candidates, documents, contract):
    """Keep revisions visible and evaluate every candidate independently.

    Multiple values for one observation require resolution before publication.
    No candidate is promoted by this report; decisions retain their provenance.
    """
    index = {(d.get("company_id"), d.get("source_url"), d.get("content_hash")): d for d in documents}
    observations = defaultdict(set)
    for row in candidates:
        observations[row.get("observation_id")].add((row.get("value"), row.get("unit")))
    rows = []
    for candidate in candidates:
        key = (candidate.get("company_id"), candidate.get("source_url"), candidate.get("source_document_hash"))
        status, reason = validate_pnc_candidate(candidate, index.get(key), contract)
        if len(observations[candidate.get("observation_id")]) > 1:
            status, reason = "rejected", "conflicting_observation_values"
        rows.append({
            "observation_id": candidate.get("observation_id"),
            "company_id": candidate.get("company_id"),
            "metric_id": candidate.get("metric_id"),
            "period_id": candidate.get("period_id"),
            "value": candidate.get("value"), "unit": candidate.get("unit"),
            "source_url": candidate.get("source_url"),
            "source_document_hash": candidate.get("source_document_hash"),
            "context": candidate.get("context"),
            "period_end": candidate.get("basis_evidence", {}).get("period_end"),
            "calendar_basis": candidate.get("basis_evidence", {}).get("calendar_basis"),
            "disclosure_scope": candidate.get("basis_evidence", {}).get("disclosure_scope"),
            "review_status": status, "reason": reason,
        })
    coverage = {
        company: {
            "candidate_count": sum(row["company_id"] == company for row in rows),
            "eligible_count": sum(row["company_id"] == company and row["review_status"] == PNC_VALIDATED_STATUS for row in rows),
        }
        for company in contract.companies
    }
    return {"candidates": rows, "coverage": coverage, "published": False}
