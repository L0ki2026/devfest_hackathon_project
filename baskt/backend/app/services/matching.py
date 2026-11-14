"""Food name normalization and match scoring."""

import re
from dataclasses import dataclass


@dataclass
class FoodCandidate:
    fdc_id: int
    description: str
    data_type: str
    score: float


PREFERRED_DATA_TYPES = (
    "Foundation",
    "SR Legacy",
    "Survey (FNDDS)",
    "Experimental",
    "Sample",
    "Demo",
)

BRANDED_TYPES = frozenset({"Branded", "Branded Food"})


def normalize_name(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def token_set(name: str) -> set[str]:
    stop = {"the", "a", "an", "and", "or", "with", "without", "raw", "fresh"}
    return {t for t in normalize_name(name).split() if t and t not in stop}


def score_match(query: str, description: str, data_type: str) -> float:
    q_tokens = token_set(query)
    d_tokens = token_set(description)
    if not q_tokens:
        return 0.0

    matched = 0
    for qt in q_tokens:
        if qt in d_tokens:
            matched += 1
            continue
        if any(qt in dt or dt in qt for dt in d_tokens):
            matched += 1
    overlap = matched / len(q_tokens)
    bonus = 0.0
    if normalize_name(query) in normalize_name(description):
        bonus += 0.15
    for i, pref in enumerate(PREFERRED_DATA_TYPES):
        if data_type == pref:
            bonus += 0.1 - i * 0.01
            break
    if data_type in BRANDED_TYPES:
        bonus -= 0.25
        extra_tokens = d_tokens - q_tokens
        if extra_tokens:
            bonus -= min(0.35, len(extra_tokens) * 0.1)

    return min(1.0, max(0.0, overlap + bonus))


def pick_best_candidate(
    query: str,
    candidates: list[FoodCandidate],
    min_confidence: float = 0.45,
) -> tuple[FoodCandidate | None, bool]:
    """Return best candidate and whether match needs confirmation."""
    if not candidates:
        return None, True

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = ranked[0]
    ambiguous = len(ranked) > 1 and (ranked[0].score - ranked[1].score) < 0.08

    if best.score < min_confidence:
        return best, True
    if ambiguous and best.score < 0.85:
        return best, True
    return best, False