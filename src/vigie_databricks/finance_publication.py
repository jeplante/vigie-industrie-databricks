"""Validation and last-known-good publication for insurer Finance candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vigie_databricks.insurer_contract import InsurerContract, parse_finance_observation_candidate


@dataclass(frozen=True)
class FinancePublicationResult:
    observations: tuple[dict[str, Any], ...]
    quality_status: str
    rejection_reasons: tuple[str, ...]


def publish_finance_candidates(
    candidates: list[dict[str, Any]],
    prior_published: list[dict[str, Any]],
    contract: InsurerContract,
) -> FinancePublicationResult:
    if not candidates:
        return FinancePublicationResult(
            tuple(prior_published),
            "stale",
            ("candidate batch is empty",),
        )
    parsed = []
    reasons = []
    for candidate in candidates:
        try:
            parsed.append(parse_finance_observation_candidate(candidate, contract))
        except ValueError as error:
            reasons.append(str(error))
    identifiers = [item.observation_id for item in parsed]
    if len(identifiers) != len(set(identifiers)):
        reasons.append("duplicate observation_id in candidate batch")
    if reasons:
        return FinancePublicationResult(tuple(prior_published), "stale", tuple(sorted(set(reasons))))
    return FinancePublicationResult(tuple(candidates), "current", ())
