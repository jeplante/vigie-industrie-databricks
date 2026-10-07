"""Which plain question a user asked, so a published-value answer can replace a model call.

A year-over-year question or a ranking is answered straight from the published rows. Any question that
also asks for an explanation is left to the model: answering only half of it would be worse than a slower
complete answer.
"""
from __future__ import annotations

import re

VARIATION = re.compile(r"variation|evolution|evolue|par rapport|annee precedente|an dernier|meme trimestre|yoy|progress|hausse|baisse|augment|diminu|recul")
RANKING = re.compile(r"meilleur|pire\b|plus eleve|plus haut|plus bas|plus faible|classement|le mieux|le moins bon|mieux que|moins bien")
EXPLANATION = re.compile(r"pourquoi|expliq|comment|important|raison|cause|risque|vigilance|que retenir|resume|situation")


def asks_for_explanation(normalized: str) -> bool:
    """A value lookup answers only half of "why", "summarise" or "what to retain": those go to the model."""
    return EXPLANATION.search(normalized) is not None


def question_intent(normalized: str) -> str | None:
    """"variation", "ranking" or None; ``normalized`` is the accent-stripped lower-case question."""
    if asks_for_explanation(normalized):
        return None
    if VARIATION.search(normalized):
        return "variation"
    if RANKING.search(normalized):
        return "ranking"
    return None
