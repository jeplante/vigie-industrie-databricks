"""Versioned domain contract for the Canadian life insurer watch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

import yaml


PERIOD_ID_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<key>Q[1-4]|AN)$")
VALID_UNITS = {"CAD_PER_SHARE", "CAD_MILLION", "CAD_BILLION", "CAD_TRILLION", "PERCENT"}
VALID_COMPARISONS = {"percent", "percentage_point"}
VALID_TRENDS = {"up", "down", "contextual"}
VALID_DOCUMENT_TYPES = {"quarterly_report", "annual_report"}
VALID_AI_PROVIDERS = {"databricks_model_serving"}
VALID_PUBLICATION_DESTINATIONS = {"databricks_app"}


@dataclass(frozen=True)
class Company:
    company_id: str
    name: str
    full_name: str
    ticker: str
    investor_relations_url: str


@dataclass(frozen=True)
class Metric:
    metric_id: str
    label: str
    unit: str
    comparison: str
    favorable_trend: str


@dataclass(frozen=True)
class FinancialSource:
    company_id: str
    source_id: str
    url: str
    allowed_hosts: tuple[str, ...]
    document_types: tuple[str, ...]


@dataclass(frozen=True)
class FinanceObservationCandidate:
    observation_id: str
    company_id: str
    metric_id: str
    period_id: str
    value: float
    unit: str
    source_url: str
    source_document_hash: str
    quality_status: str


@dataclass(frozen=True)
class ReportingPeriod:
    period_id: str
    year: int
    period_key: str


@dataclass(frozen=True)
class FinancePolicy:
    raw_content_retention_days: int
    failed_document_retention_days: int
    stale_audit_retention_days: int
    raw_content_volume: str
    ai_provider: str
    ai_model: str
    ai_max_calls_per_run: int
    publication_destination: str
    live_network_enabled_by_default: bool


@dataclass(frozen=True)
class InsurerContract:
    companies: dict[str, Company]
    metrics: dict[str, Metric]
    financial_sources: dict[str, FinancialSource]
    finance_policy: FinancePolicy


def parse_period_id(period_id: str) -> ReportingPeriod:
    match = PERIOD_ID_PATTERN.fullmatch(period_id)
    if not match:
        raise ValueError("period_id must use YYYY-Q1 through YYYY-Q4 or YYYY-AN")
    return ReportingPeriod(period_id, int(match["year"]), match["key"])


def load_insurer_contract(config_directory: Path) -> InsurerContract:
    companies_data = _load_mapping(config_directory / "companies.yaml", "companies")
    metrics_data = _load_mapping(config_directory / "metrics.yaml", "metrics")
    sources_data = _load_mapping(config_directory / "sources.yaml", "financial_documents")

    companies = {
        company_id: Company(
            company_id=company_id,
            name=_required_string(values, "name", f"companies.{company_id}"),
            full_name=_required_string(values, "full_name", f"companies.{company_id}"),
            ticker=_required_string(values, "ticker", f"companies.{company_id}"),
            investor_relations_url=_https_url(
                _required_string(values, "investor_relations_url", f"companies.{company_id}"),
                f"companies.{company_id}.investor_relations_url",
            ),
        )
        for company_id, values in companies_data.items()
    }
    metrics = {
        metric_id: _metric(metric_id, values)
        for metric_id, values in metrics_data.items()
    }
    sources = {
        company_id: _source(company_id, values)
        for company_id, values in sources_data.items()
    }
    if set(companies) != set(sources):
        raise ValueError("financial_documents must define exactly one source for every company")
    policy_data = _load_object(config_directory / "finance_policy.yaml", "finance_policy")
    return InsurerContract(companies, metrics, sources, _finance_policy(policy_data))


def parse_finance_observation_candidate(
    value: dict[str, Any], contract: InsurerContract
) -> FinanceObservationCandidate:
    company_id = _required_string(value, "company_id", "candidate")
    metric_id = _required_string(value, "metric_id", "candidate")
    period_id = _required_string(value, "period_id", "candidate")
    if company_id not in contract.companies:
        raise ValueError("candidate.company_id is not configured")
    if metric_id not in contract.metrics:
        raise ValueError("candidate.metric_id is not configured")
    parse_period_id(period_id)
    unit = _required_string(value, "unit", "candidate")
    if unit != contract.metrics[metric_id].unit:
        raise ValueError("candidate.unit does not match the configured metric")
    source_url = _https_url(_required_string(value, "source_url", "candidate"), "candidate.source_url")
    if urlparse(source_url).hostname not in contract.financial_sources[company_id].allowed_hosts:
        raise ValueError("candidate.source_url host is not approved for the company")
    observation_id = _required_string(value, "observation_id", "candidate")
    expected_id = f"{company_id}-{period_id}-{metric_id}"
    if observation_id != expected_id:
        raise ValueError("candidate.observation_id does not match its domain identifiers")
    raw_value = value.get("value")
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        raise ValueError("candidate.value must be numeric")
    quality_status = _required_string(value, "quality_status", "candidate")
    if quality_status != "candidate":
        raise ValueError("candidate.quality_status must be candidate")
    return FinanceObservationCandidate(
        observation_id,
        company_id,
        metric_id,
        period_id,
        float(raw_value),
        unit,
        source_url,
        _required_string(value, "source_document_hash", "candidate"),
        quality_status,
    )


def _load_mapping(path: Path, key: str) -> dict[str, dict[str, Any]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read contract file: {path}") from error
    if not isinstance(data, dict) or not isinstance(data.get(key), dict) or not data[key]:
        raise ValueError(f"{path.name} must contain a non-empty {key} mapping")
    result = data[key]
    if not all(isinstance(item_key, str) and isinstance(value, dict) for item_key, value in result.items()):
        raise ValueError(f"{path.name} contains an invalid {key} entry")
    return result


def _load_object(path: Path, key: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read contract file: {path}") from error
    if not isinstance(data, dict) or not isinstance(data.get(key), dict) or not data[key]:
        raise ValueError(f"{path.name} must contain a non-empty {key} mapping")
    return data[key]


def _required_string(values: dict[str, Any], key: str, context: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _https_url(value: str, context: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{context} must be an absolute HTTPS URL")
    return value


def _metric(metric_id: str, values: dict[str, Any]) -> Metric:
    context = f"metrics.{metric_id}"
    unit = _required_string(values, "unit", context)
    comparison = _required_string(values, "comparison", context)
    favorable_trend = _required_string(values, "favorable_trend", context)
    if unit not in VALID_UNITS:
        raise ValueError(f"{context}.unit is unsupported")
    if comparison not in VALID_COMPARISONS:
        raise ValueError(f"{context}.comparison is unsupported")
    if favorable_trend not in VALID_TRENDS:
        raise ValueError(f"{context}.favorable_trend is unsupported")
    return Metric(metric_id, _required_string(values, "label", context), unit, comparison, favorable_trend)


def _source(company_id: str, values: dict[str, Any]) -> FinancialSource:
    context = f"financial_documents.{company_id}"
    url = _https_url(_required_string(values, "url", context), context + ".url")
    hosts = values.get("allowed_hosts")
    document_types = values.get("document_types")
    if not isinstance(hosts, list) or not hosts or not all(isinstance(host, str) and host for host in hosts):
        raise ValueError(f"{context}.allowed_hosts must be a non-empty list of hosts")
    if urlparse(url).hostname not in hosts:
        raise ValueError(f"{context}.url host must appear in allowed_hosts")
    if not isinstance(document_types, list) or not document_types or set(document_types) - VALID_DOCUMENT_TYPES:
        raise ValueError(f"{context}.document_types contains an unsupported type")
    return FinancialSource(
        company_id,
        _required_string(values, "source_id", context),
        url,
        tuple(hosts),
        tuple(document_types),
    )


def _finance_policy(values: dict[str, Any]) -> FinancePolicy:
    retention_days = values.get("raw_content_retention_days")
    failed_retention_days = values.get("failed_document_retention_days")
    stale_retention_days = values.get("stale_audit_retention_days")
    max_calls = values.get("ai_max_calls_per_run")
    live_default = values.get("live_network_enabled_by_default")
    volume = _required_string(values, "raw_content_volume", "finance_policy")
    provider = _required_string(values, "ai_provider", "finance_policy")
    destination = _required_string(values, "publication_destination", "finance_policy")
    if not isinstance(retention_days, int) or isinstance(retention_days, bool) or not 1 <= retention_days <= 3650:
        raise ValueError("finance_policy.raw_content_retention_days must be between 1 and 3650")
    if not isinstance(failed_retention_days, int) or not 1 <= failed_retention_days <= 3650:
        raise ValueError("finance_policy.failed_document_retention_days must be between 1 and 3650")
    if not isinstance(stale_retention_days, int) or not 1 <= stale_retention_days <= 3650:
        raise ValueError("finance_policy.stale_audit_retention_days must be between 1 and 3650")
    if not volume.startswith("/Volumes/"):
        raise ValueError("finance_policy.raw_content_volume must be a Unity Catalog volume path")
    if provider not in VALID_AI_PROVIDERS:
        raise ValueError("finance_policy.ai_provider is unsupported")
    if not isinstance(max_calls, int) or isinstance(max_calls, bool) or not 0 <= max_calls <= 100:
        raise ValueError("finance_policy.ai_max_calls_per_run must be between 0 and 100")
    if destination not in VALID_PUBLICATION_DESTINATIONS:
        raise ValueError("finance_policy.publication_destination is unsupported")
    if not isinstance(live_default, bool):
        raise ValueError("finance_policy.live_network_enabled_by_default must be boolean")
    return FinancePolicy(
        retention_days,
        failed_retention_days,
        stale_retention_days,
        volume.rstrip("/"),
        provider,
        _required_string(values, "ai_model", "finance_policy"),
        max_calls,
        destination,
        live_default,
    )
