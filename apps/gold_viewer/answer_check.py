"""Cross-check the figures a model wrote against the figures it was given.

The chat guardrails already drop citations and KPIs that are not in the context. This adds a check on
the numbers in the prose: a figure followed by a unit (%, pp, $, millions, milliards...) must be traceable
to a value of the context, to a unit conversion of it, or to a difference or percentage change between
two values of the same series. It catches invented numbers.

``mislabelled_figures`` adds the second check: a real figure attached to the wrong indicator (a combined
ratio written as the claims ratio, the error observed on 2026-10-07). A figure is flagged only when the
indicator named just before it cannot explain it while another indicator's value does. Neither check is a
proof of correctness; both are shown to the reader, never used to block an answer.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

UNIT = r"(?:%|pp\b|\$|G\$|M\$|T\$|millions?\b|milliards?\b|billions?\b|mds\b|M\b|B\b)"
FIGURE = re.compile(rf"(?<![\w.,])([-+]?\d+(?:[   ]\d{{3}})*(?:[.,]\d+)?)\s*({UNIT})", re.IGNORECASE)
# Unit conversions between what the context stores (billions, fractions) and what a sentence may say.
SCALES = (1, 100, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9)


def _leaves(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _leaves(item)


def _series(context: Any) -> list[list[float]]:
    """Values of one (company, metric) across periods: the differences between them are legitimate figures."""
    rows: list[dict[str, Any]] = []
    if isinstance(context, dict):
        for key in ("observations", "comparisons"):
            rows += [row for row in context.get(key, []) if isinstance(row, dict)]
    grouped: dict[tuple[Any, Any], list[float]] = {}
    for row in rows:
        for field in ("value", "current_value", "previous_value"):
            if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool):
                grouped.setdefault((row.get("company_id"), row.get("metric_id")), []).append(float(row[field]))
    return list(grouped.values())


def allowed_figures(context: Any) -> list[float]:
    values = set(_leaves(context))
    for series in _series(context):
        for first in series:
            for second in series:
                if first != second:
                    values.add(first - second)
                    if second:
                        values.add((first - second) / abs(second) * 100)
    return sorted(values)


def _parse(raw: str) -> tuple[float, int]:
    cleaned = re.sub(r"[   ]", "", raw).replace(",", ".")
    decimals = len(cleaned.split(".")[1]) if "." in cleaned else 0
    return abs(float(cleaned)), decimals


def unsupported_figures(text: str, context: Any) -> list[str]:
    """Figures with a unit in ``text`` that no value of ``context`` explains (empty list = all traced)."""
    allowed = [abs(value) for value in allowed_figures(context)]
    unsupported = []
    for match in FIGURE.finditer(text or ""):
        number, decimals = _parse(match.group(1))
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(candidate * scale - number) <= tolerance for candidate in allowed for scale in SCALES):
            unsupported.append(match.group(0).strip())
    return list(dict.fromkeys(unsupported))


# Indicator names as a French or English answer writes them, accent-stripped and lower case. Short forms
# ("sinistres", "frais") matter: in "ratio combiné 93,9 %, sinistres 64,2 %" the second figure is the claims ratio.
METRIC_NAMES: dict[str, tuple[str, ...]] = {
    "core_eps": ("bpa", "benefice par action", "benefice de base par action", "eps"),
    "core_earnings": ("resultat des activites de base", "resultats des activites de base", "benefice de base",
                      "benefices de base", "activites de base", "core earnings"),
    "net_income": ("resultat net", "benefice net", "revenu net", "net income", "perte nette"),
    "licat_ratio": ("licat", "ratio de capital", "solvabilite"),
    "solvency_ratio": ("licat", "ratio de capital", "solvabilite"),
    "assets_under_management": ("actifs geres", "actifs sous gestion", "actifs administres", "actifs"),
    "assets_under_administration": ("actifs geres", "actifs sous gestion", "actifs administres", "actifs"),
    "total_client_assets": ("actifs geres", "actifs sous gestion", "actifs administres", "actifs"),
    "core_roe": ("rendement des capitaux propres", "roe"),
    "insurance_revenue": ("produit d assurance", "revenu d assurance", "produits des activites d assurance", "insurance revenue"),
    "combined_ratio": ("ratio combine", "ratios combines", "combined ratio"),
    "claims_ratio": ("ratio de sinistres", "ratios de sinistres", "sinistralite", "sinistres", "claims ratio"),
    "expense_ratio": ("ratio de frais", "ratio des frais", "ratios de frais", "frais", "expense ratio"),
    "operating_income": ("resultat net operationnel", "resultat net d exploitation", "resultat operationnel", "benefice operationnel",
                         "resultat d exploitation", "operating income", "operating net income"),
}
_BOUNDARY = re.compile(r"[;!?\n]|\.\s")


def _plain(text: str) -> str:
    text = text.replace("’", " ").replace("'", " ")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _named_metrics(segment: str) -> set[str] | None:
    """Metrics of the indicator named last in ``segment`` (several ids can share a name), or None."""
    plain = _plain(segment)
    best: tuple[int, int] | None = None
    names: set[str] = set()
    for metric, aliases in METRIC_NAMES.items():
        for alias in aliases:
            # every word may carry a plural "s" ("ratios combinés", "revenus d'assurance")
            pattern = r"\s+".join(f"{re.escape(word)}s?" for word in alias.split())
            for match in re.finditer(rf"\b{pattern}\b", plain):
                rank = (match.end(), len(alias))
                if best is None or rank > best:
                    best, names = rank, {metric}
                elif rank == best:
                    names.add(metric)
    return names or None


def _metric_values(context: Any) -> dict[str, list[list[float]]]:
    """Per metric, the series of values of each company (current, previous, history)."""
    rows: list[dict[str, Any]] = []
    if isinstance(context, dict):
        for key in ("observations", "comparisons"):
            rows += [row for row in context.get(key, []) if isinstance(row, dict)]
    series: dict[tuple[Any, Any], list[float]] = {}
    for row in rows:
        for field in ("value", "current_value", "previous_value"):
            value = row.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                series.setdefault((row.get("company_id"), row.get("metric_id")), []).append(float(value))
    result: dict[str, list[list[float]]] = {}
    for (_company, metric), values in series.items():
        result.setdefault(str(metric), []).append(values)
    return result


def _explains(number: float, tolerance: float, values: Iterable[float]) -> bool:
    return any(abs(abs(value) * scale - number) <= tolerance for value in values for scale in SCALES)


def _derived(series_list: list[list[float]]) -> list[float]:
    values = []
    for series in series_list:
        values += series
        for first in series:
            for second in series:
                if first != second:
                    values.append(first - second)
                    if second:
                        values.append((first - second) / abs(second) * 100)
    return values


def _sentence_start(text: str, position: int) -> int:
    start = 0
    for boundary in _BOUNDARY.finditer(text, 0, position):
        start = boundary.end()
    return start


# A name right after a figure, introduced by "de" ("1,7937 G$ de revenus d'assurance"), names that figure.
_NAME_AFTER = re.compile(r"\s*(?:cad|de dollars)?\s*(?:de|d)\s+")
NAME_AFTER_CHARS = 40

# The words since the previous figure name the next one; a short list separator (", DFY ", " et celui de
# Definity de ", ", SLF = ") inherits the indicator of the previous figure of the same sentence.
LIST_SEPARATOR_CHARS = 30


def mislabelled_figures(text: str, context: Any) -> list[str]:
    """Figures that belong to another indicator than the one the sentence names (empty list = none found).

    A name is read only among the indicators the context holds: "résultat d'exploitation" means the core
    earnings of a life insurer and the operating income of a P&C insurer."""
    by_metric = _metric_values(context)
    flagged = []
    previous_end, previous_sentence, previous_named = 0, -1, None
    for match in FIGURE.finditer(text or ""):
        start = match.start()
        sentence_start = _sentence_start(text, start)
        segment = text[max(sentence_start, previous_end):start]
        following = text[match.end():match.end() + NAME_AFTER_CHARS]
        lead = _NAME_AFTER.match(_plain(following))
        named = _named_metrics(following[:lead.end() + 30]) if lead else None
        if named:  # only when the name starts right after "de"
            first = min((m.start() for metric in named for alias in METRIC_NAMES[metric]
                         for m in re.finditer(r"\s+".join(f"{re.escape(w)}s?" for w in alias.split()), _plain(following))), default=None)
            named = named if first == lead.end() else None
        named = named or _named_metrics(segment)
        named = named & set(by_metric) if named else None
        if not named and len(segment.strip()) <= LIST_SEPARATOR_CHARS and previous_sentence == sentence_start:
            named = previous_named
        previous_end, previous_sentence, previous_named = match.end(), sentence_start, named
        if "respectivement" in _plain(text[sentence_start:sentence_start + 400]):
            continue  # "ratios combinés, de sinistres et de frais respectivement de 93,9 %, 64,2 % et 29,7 %"
        if not named:
            continue
        number, decimals = _parse(match.group(1))
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if any(_explains(number, tolerance, _derived(by_metric.get(metric, []))) for metric in named):
            continue
        owners = sorted(metric for metric, series in by_metric.items()
                        if metric not in named and _explains(number, tolerance, (v for values in series for v in values)))
        if owners:
            flagged.append(f"{match.group(0).strip()} ({' / '.join(owners)})")
    return list(dict.fromkeys(flagged))


# Each metric's stored unit, in CAD billions, so a figure's written unit can be checked. Life amounts are
# stored in billions except total client assets (trillions); P&C rows carry their own unit.
STORED_SCALE = {"total_client_assets": 1e3}
MONEY_UNITS = {"g$": 1.0, "milliard": 1.0, "milliards": 1.0, "md": 1.0, "mds": 1.0, "billion": 1.0, "billions": 1.0, "b": 1.0,
               "m$": 1e-3, "million": 1e-3, "millions": 1e-3, "m": 1e-3, "t$": 1e3}
_AFTER_DOLLAR = re.compile(r"\s*(milliards?|millions?|mds?|billions?)\b", re.IGNORECASE)
AMOUNT_METRICS = {"core_earnings", "net_income", "assets_under_management", "assets_under_administration",
                  "total_client_assets", "insurance_revenue", "operating_income", "new_business_value", "ape_sales"}


def _amounts(context: Any) -> list[float]:
    """Amount values of the context, in CAD billions."""
    rows: list[dict[str, Any]] = []
    if isinstance(context, dict):
        for key in ("observations", "comparisons"):
            rows += [row for row in context.get(key, []) if isinstance(row, dict)]
    amounts = []
    for row in rows:
        metric = str(row.get("metric_id"))
        if metric not in AMOUNT_METRICS and row.get("unit") != "CAD_BILLION":
            continue
        for field in ("value", "current_value", "previous_value"):
            value = row.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                amounts.append(abs(float(value)) * STORED_SCALE.get(metric, 1.0))
    return amounts


def misscaled_figures(text: str, context: Any) -> list[str]:
    """Amounts written with the wrong unit: the number is a published amount, but in millions instead of
    billions, billions instead of trillions, and so on (empty list = none found)."""
    amounts = _amounts(context)
    per_share = [abs(float(row[field])) for key in ("observations", "comparisons") for row in (context or {}).get(key, [])
                 if isinstance(row, dict) and row.get("metric_id") == "core_eps"
                 for field in ("value", "current_value", "previous_value") if isinstance(row.get(field), (int, float))]
    flagged = []
    for match in FIGURE.finditer(text or ""):
        after = None
        unit = match.group(2).lower()
        if unit == "$":
            after = _AFTER_DOLLAR.match(text, match.end())
            if not after:
                continue  # a bare dollar figure is a per-share amount
            unit = after.group(1).lower()
        if unit not in MONEY_UNITS:
            continue
        number, decimals = _parse(match.group(1))
        written = number * MONEY_UNITS[unit]
        tolerance = (0.5 * 10 ** (-decimals) + 1e-9) * MONEY_UNITS[unit]
        if any(abs(amount - written) <= tolerance for amount in amounts):
            continue
        candidates = [amount * scale for amount in amounts for scale in (1, 1e3, 1e-3, 1e6)] + per_share
        if any(abs(candidate - number) <= 0.5 * 10 ** (-decimals) + 1e-9 for candidate in candidates):
            flagged.append(match.group(0).strip() + (after.group(0) if after else ""))
    return list(dict.fromkeys(flagged))


COMPANY_NAMES = {
    "MFC": ("manuvie", "manulife", "mfc", "john hancock"), "SLF": ("sun life", "slf"),
    "GWO": ("great-west", "great west", "gwo", "canada life"), "IAG": ("ia", "iag", "industrielle alliance", "industrial alliance"),
    "IFC": ("intact", "ifc"), "DFY": ("definity", "dfy"), "TD": ("td",), "AV": ("aviva", "av"),
}
COMPANY_AFTER_CHARS = 30
# An issuer named after a figure owns it only through "pour", "chez" or a parenthesis ("1,90 $ pour
# Manuvie"); otherwise the name opens the next clause ("17,5 % tandis que celle de Manuvie ...").
_OWNER_AFTER = re.compile(r"\s*(?:milliards?|millions?|cad|de dollars|par action)?\s*(?:\(|pour|chez)\s*(?:l\s|la\s|le\s)?")


def _company_mentions(plain: str) -> list[tuple[int, int, str]]:
    found = []
    for company, names in COMPANY_NAMES.items():
        for name in names:
            for match in re.finditer(rf"\b{re.escape(name)}\b", plain):
                found.append((match.start(), match.end(), company))
    return sorted(found)


def misattributed_figures(text: str, context: Any) -> list[str]:
    """Figures attributed to an issuer whose published values cannot explain them, while another issuer's
    value does ("le revenu d'assurance d'Intact de 1,7937 G$" when that is Definity's). Empty list = none."""
    rows: list[dict[str, Any]] = []
    if isinstance(context, dict):
        for key in ("observations", "comparisons"):
            rows += [row for row in context.get(key, []) if isinstance(row, dict)]
    series: dict[str, list[list[float]]] = {}
    for company in {str(row.get("company_id")) for row in rows}:
        per_metric: dict[Any, list[float]] = {}
        for row in rows:
            if str(row.get("company_id")) != company:
                continue
            for field in ("value", "current_value", "previous_value"):
                value = row.get(field)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    per_metric.setdefault(row.get("metric_id"), []).append(float(value))
        series[company] = list(per_metric.values())
    # one plain character per text character, so positions match the figures found in ``text``
    plain = "".join(_plain(character)[:1] or " " for character in (text or ""))
    mentions = _company_mentions(plain)
    flagged = []
    previous_end = 0
    for match in FIGURE.finditer(text or ""):
        sentence_start = _sentence_start(text, match.start())
        after = [company for start, _end, company in mentions if match.end() <= start <= match.end() + COMPANY_AFTER_CHARS
                 and _OWNER_AFTER.fullmatch(plain[match.end():start])]
        before = [company for _start, end, company in mentions if end <= match.start()]
        since_previous = [company for start, end, company in mentions if max(previous_end, sentence_start) <= start and end <= match.start()]
        in_sentence = {company for start, end, company in mentions if sentence_start <= start and end <= match.start()}
        previous_end = match.end()
        if after:
            named = after[0]
        elif len(set(since_previous)) > 1 or (not since_previous and len(in_sentence) > 1):
            continue  # "IFC et DFY ont des ratios proches (94,9 % et 93,9 %)": the pairing is not written
        elif since_previous:
            named = since_previous[-1]
        else:
            named = before[-1] if before else None
        if named is None or named not in series:
            continue
        number, decimals = _parse(match.group(1))
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        if _explains(number, tolerance, _derived(series[named])):
            continue
        owners = sorted(company for company, values in series.items()
                        if company != named and _explains(number, tolerance, (v for s in values for v in s)))
        if owners:
            flagged.append(f"{match.group(0).strip()} ({'/'.join(owners)}, pas {named})")
    return list(dict.fromkeys(flagged))
