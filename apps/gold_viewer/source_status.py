"""Per-source health rows for the sidebar: which source is fine, late or failing, and why."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from typing import Any, Iterable, Mapping

OK_ACQUISITION = {"fetched", "unchanged"}
# Finance runs daily, official news every six hours.
FINANCE_WARN_HOURS, FINANCE_ERROR_HOURS = 36, 96
NEWS_WARN_HOURS, NEWS_ERROR_HOURS = 18, 72
LEVEL_LABEL = {"ok": "OK", "warn": "À vérifier", "error": "Problème"}


@dataclass(frozen=True)
class SourceRow:
    name: str
    level: str  # "ok" | "warn" | "error"
    text: str


def format_time(value: Any) -> str:
    """UTC minute precision, tolerant to strings, datetimes and missing values."""
    if value in (None, ""):
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    text = str(value)
    return text[:16].replace("T", " ") if len(text) >= 16 else text


def _age_hours(value: Any, now: datetime) -> float | None:
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (now - value).total_seconds() / 3600


def audit_freshness_row(label: str, audit: Mapping[str, Any] | None, now: datetime, warn_hours: int, error_hours: int) -> SourceRow | None:
    """Flag a pipeline whose last recorded run is too old (a run may succeed yet persist nothing)."""
    if not audit:
        return SourceRow(label, "error", "Aucun run enregistré")
    age = _age_hours(audit.get("observed_at"), now)
    if age is None:
        return None
    stamp = f"{format_time(audit.get('observed_at'))} UTC"
    if age > error_hours:
        return SourceRow(label, "error", f"Dernier run enregistré il y a {age / 24:.0f} j ({stamp})")
    if age > warn_hours:
        return SourceRow(label, "warn", f"Dernier run enregistré il y a {age:.0f} h ({stamp})")
    return None


def finance_sources(
    companies: Iterable[str],
    latest_documents: Mapping[str, Mapping[str, Any] | None],
    latest_attempts: Mapping[str, Mapping[str, Any]],
    current_period: str | None,
) -> list[SourceRow]:
    rows = []
    for company in companies:
        document, attempt = latest_documents.get(company), latest_attempts.get(company)
        period = document.get("reporting_period") if document else None
        if attempt and attempt.get("acquisition_status") not in OK_ACQUISITION:
            reason = attempt.get("error_code") or attempt.get("acquisition_status") or "inconnu"
            last_good = f" · dernier document valide : {period}" if period else ""
            rows.append(SourceRow(company, "error", f"Échec de collecte ({reason}){last_good}"))
        elif not document:
            rows.append(SourceRow(company, "error", "Aucun document collecté"))
        elif current_period and period != current_period:
            rows.append(SourceRow(company, "warn", f"Période {period} · attendue {current_period}"))
        else:
            rows.append(SourceRow(company, "ok", f"{period} · à jour · collecté {format_time(document.get('fetched_at'))}"))
    return rows


def news_sources(
    companies: Iterable[str],
    counts: Mapping[str, Mapping[str, Any]],
    audit: Mapping[str, Any] | None,
    total_sources: int = 4,
) -> list[SourceRow]:
    rows = []
    succeeded = int(audit.get("sources_succeeded") or 0) if audit else None
    if succeeded is not None and succeeded < total_sources:
        rows.append(SourceRow("Dernier run", "warn",
                              f"{succeeded}/{total_sources} sources ont répondu (la source en échec n'est pas détaillée par l'audit)"))
    for company in companies:
        entry = counts.get(company)
        number = int(entry.get("n") or 0) if entry else 0
        if number == 0:
            rows.append(SourceRow(company, "warn", "Aucun article enregistré"))
        else:
            plural = "s" if number > 1 else ""
            rows.append(SourceRow(company, "ok", f"{number} article{plural} · dernier ajout {format_time(entry.get('last_fetch'))}"))
    return rows


def alert_rows(alerts: Iterable[Mapping[str, Any]]) -> list[SourceRow]:
    return [SourceRow(str(alert.get("entity") or "Exploitation"), "error", str(alert.get("message") or ""))
            for alert in alerts if alert.get("status") == "alert"]


def worst_level(rows: Iterable[SourceRow]) -> str:
    levels = {row.level for row in rows}
    return "error" if "error" in levels else "warn" if "warn" in levels else "ok"


def source_list_html(rows: Iterable[SourceRow]) -> str:
    """Accessible list: the status is written out, never carried by colour alone."""
    items = "".join(
        f"<li class='source-row source-{escape(row.level)}'>"
        f"<span class='source-state'>{escape(LEVEL_LABEL.get(row.level, row.level))}</span>"
        f"<strong>{escape(row.name)}</strong><span class='source-text'>{escape(row.text)}</span></li>"
        for row in rows
    )
    return f"<ul class='source-list'>{items}</ul>" if items else ""
