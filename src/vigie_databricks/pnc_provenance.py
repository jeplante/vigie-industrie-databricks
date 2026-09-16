"""P&C-specific source-basis safeguards.

These controls intentionally sit apart from the life/wealth pipeline. A source
may be official yet still be incomparable when it represents a global group or
a combined bank segment rather than Canadian P&C operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from vigie_databricks.insurer_contract import InsurerContract


@dataclass(frozen=True)
class PncSourceBasis:
    company_id: str
    disclosure_scope: str
    required_context: tuple[str, ...]
    prohibited_context: tuple[str, ...] = ()


PNC_SOURCE_BASIS: dict[str, PncSourceBasis] = {
    "IFC": PncSourceBasis("IFC", "Intact consolidated P&C operations", ("intact",)),
    "DFY": PncSourceBasis("DFY", "Definity consolidated Canadian P&C operations", ("definity",)),
    "AV": PncSourceBasis("AV", "Aviva Canada general-insurance segment", ("canada",)),
    "TD": PncSourceBasis(
        "TD", "TD Insurance standalone line", ("insurance",), ("wealth management and insurance",)
    ),
}


def validate_pnc_source_basis(
    company_id: str, source_url: str, context: str, contract: InsurerContract
) -> tuple[bool, str | None]:
    """Verify allowlisted provenance plus company-specific disclosure scope."""
    if company_id not in PNC_SOURCE_BASIS or company_id not in contract.financial_sources:
        return False, "pnc_company_not_configured"
    hostname = urlparse(source_url).hostname
    allowed_hosts = contract.financial_sources[company_id].allowed_hosts
    if hostname not in allowed_hosts:
        return False, "pnc_source_host_not_allowlisted"
    normalized_context = " ".join(context.lower().split())
    basis = PNC_SOURCE_BASIS[company_id]
    if any(prohibited in normalized_context for prohibited in basis.prohibited_context):
        return False, "pnc_disclosure_scope_prohibited"
    if not all(required in normalized_context for required in basis.required_context):
        return False, "pnc_disclosure_scope_missing"
    return True, None
