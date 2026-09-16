"""Deterministic candidate extraction for the isolated Canadian P&C domain."""

from __future__ import annotations

import re

from vigie_databricks.finance_extraction import ExtractedMetric, _normalized_value
from vigie_databricks.insurer_contract import InsurerContract


PNC_ALIASES = {
    "IFC": {
        "insurance_revenue": ("insurance revenue",),
        "combined_ratio": ("combined ratio",),
        "claims_ratio": ("claims ratio",),
        "expense_ratio": ("expense ratio",),
        "catastrophe_losses": ("catastrophe losses", "catastrophe loss"),
        "operating_income": ("operating net income",),
        "net_income": ("net operating income",),
        "operating_roe": ("operating ROE", "return on equity"),
    },
    "DFY": {
        "insurance_revenue": ("insurance revenue",),
        "combined_ratio": ("combined ratio",),
        "claims_ratio": ("claims ratio",),
        "expense_ratio": ("expense ratio",),
        "catastrophe_losses": ("catastrophe losses",),
        "operating_income": ("operating income",),
        "net_income": ("net income",),
        "operating_roe": ("operating ROE",),
    },
    "AV": {
        "insurance_revenue": ("Canada insurance revenue",),
        "combined_ratio": ("Canada combined operating ratio", "Canada combined ratio"),
        "operating_income": ("Canada operating profit",),
    },
    "TD": {
        "catastrophe_losses": ("catastrophe claims",),
        "net_income": ("Insurance net income",),
        "operating_roe": ("Return on common equity – Insurance",),
    },
}

_NUMBER = r"\d{1,3}(?:[, ]\d{3})+|\d+(?:[.,]\d+)?"
_VALUE = re.compile(rf"(?P<number>{_NUMBER})\s*(?P<unit>%|million|billion|\$)", re.IGNORECASE)


def extract_pnc_metrics(company_id: str, content: str, contract: InsurerContract) -> list[ExtractedMetric]:
    """Extract only explicitly labelled P&C candidates from an issuer's report."""
    if company_id not in PNC_ALIASES or company_id not in contract.companies:
        raise ValueError("company_id has no configured P&C extractor")
    text = re.sub(r"\s+", " ", content).strip()
    extracted: list[ExtractedMetric] = []
    for metric_id, aliases in PNC_ALIASES[company_id].items():
        if metric_id not in contract.metrics:
            continue
        expected_unit = contract.metrics[metric_id].unit
        for alias in aliases:
            for match in re.finditer(re.escape(alias), text, re.IGNORECASE):
                # TD's combined Wealth Management and Insurance segment is not
                # a comparable P&C value; accept only the standalone Insurance line.
                preceding = text[:match.start()].rsplit(".", 1)[-1].lower()
                if company_id == "TD" and metric_id == "net_income" and "wealth management" in preceding:
                    continue
                context = text[match.start():match.end() + 120]
                value_match = _VALUE.search(context[len(alias):])
                if not value_match:
                    continue
                value = _normalized_value(value_match.group("number"), value_match.group("unit"), expected_unit)
                if value is not None:
                    extracted.append(ExtractedMetric(metric_id, value, expected_unit, value_match.group(0), context))
                    break
            else:
                continue
            break
    return extracted
