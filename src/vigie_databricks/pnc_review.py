"""Build an explicit review queue without approving extraction candidates."""

from collections import defaultdict
import math
import re

from vigie_databricks.pnc_history import validate_pnc_candidate, PNC_VALIDATED_STATUS


def select_reviewed_periods(reviews, periods=None):
    """Select review records for explicit quarterly periods, preserving order."""
    reviews = list(reviews)
    if periods is None:
        return reviews
    periods = list(periods)
    if not periods or any(not isinstance(period, str) or
                          not re.fullmatch(r"20\d{2}-Q[1-4]", period) for period in periods):
        raise ValueError("period selection must contain valid quarterly period IDs")
    if len(set(periods)) != len(periods):
        raise ValueError("period selection contains duplicates")
    selected = [review for review in reviews if review.get("period_id") in set(periods)]
    matched = {review.get("period_id") for review in selected}
    missing = set(periods) - matched
    if missing:
        raise ValueError(f"no reviewed evidence for requested periods: {', '.join(sorted(missing))}")
    return selected


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


def collapse_identical_candidates(candidates):
    """Drop re-persisted copies of one candidate, keeping the first occurrence.

    Repeated acquisition runs append the same extraction to staging. Only rows that agree
    on observation, document revision, value and unit are collapsed; a conflicting value or
    a different revision under the same observation is kept so the publication guard rejects it.
    """
    seen, result = set(), []
    for candidate in candidates:
        key = (candidate.get("observation_id"), candidate.get("source_document_hash"),
               candidate.get("value"), candidate.get("unit"))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
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
