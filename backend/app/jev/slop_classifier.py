"""Deterministic synthetic slop classifier: perplexity, burstiness, density, clichés."""

import math
import re
from collections import Counter
from typing import Optional

from pydantic import BaseModel

from app.jev.schemas import JEVAttackIndexMetrics, AdmiraltyReliability

# Common AI-generated transitional clichés / slop markers
SLOP_CLICHES = [
    "in today's fast-paced world",
    "in today's rapidly evolving",
    "the rise of",
    "a game changer",
    "testament to",
    "deeply",
    "unlock",
    "revolutionize",
    "landscape",
    "delve into",
    "it's important to note",
    "it's worth mentioning",
    "in conclusion",
    "overall",
    "leverage",
    "synergy",
    "paradigm shift",
    "holistic approach",
    "cutting-edge",
    "state-of-the-art",
    "seamlessly",
    "not only but also",
]


class SlopClassifierResult(BaseModel):
    slop_probability: float
    perplexity: float
    burstiness: float
    info_density: float
    cliche_count: int
    token_count: int


def _tokenize(text: str) -> list[str]:
    return [t.strip(".,!?;:\"'()[]{}").lower() for t in text.split() if t.strip()]


def _compute_perplexity(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    probs = [c / total for c in counts.values()]
    log_sum = sum(math.log2(p) for p in probs if p > 0)
    perplexity = 2 ** (-log_sum / len(probs)) if probs else 0.0
    return perplexity


def _compute_burstiness(tokens: list[str]) -> float:
    if len(tokens) < 2:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    variance = (
        sum(((counts[t] / total) - (1 / len(counts))) ** 2 for t in counts) if counts else 0.0
    )
    return variance**0.5


def _compute_info_density(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    unique_terms = len(set(tokens))
    atomic_claims = len(re.findall(r"[.!?]", text))  # sentence count as proxy
    return min(1.0, (unique_terms + atomic_claims) / len(tokens))


def _count_cliches(text: str) -> int:
    text_lower = text.lower()
    return sum(1 for c in SLOP_CLICHES if c in text_lower)


def classify_slop(
    text: str, admiralty_reliability: str = "F_CANNOT_BE_JUDGED"
) -> SlopClassifierResult:
    tokens = _tokenize(text)
    if not tokens:
        return SlopClassifierResult(
            slop_probability=1.0,
            perplexity=0.0,
            burstiness=0.0,
            info_density=0.0,
            cliche_count=0,
            token_count=0,
        )

    perplexity = _compute_perplexity(tokens)
    burstiness = _compute_burstiness(tokens)
    info_density = _compute_info_density(tokens, text)
    cliche_count = _count_cliches(text)

    # Weighted slop score: high perplexity, low density, high clichés → slop
    density_penalty = max(0.0, 1.0 - info_density) * 0.4
    cliche_penalty = min(1.0, cliche_count / 10.0) * 0.3
    perplexity_penalty = min(1.0, perplexity / 100.0) * 0.3

    slop_probability = density_penalty + cliche_penalty + perplexity_penalty

    # Admiralty reliability can nudge the score
    if admiralty_reliability in ("A_COMPLETELY_RELIABLE", "B_USUALLY_RELIABLE"):
        slop_probability *= 0.5
    elif admiralty_reliability in ("E_UNRELIABLE", "F_CANNOT_BE_JUDGED"):
        slop_probability = min(1.0, slop_probability * 1.2)

    slop_probability = min(1.0, max(0.0, slop_probability))

    return SlopClassifierResult(
        slop_probability=slop_probability,
        perplexity=perplexity,
        burstiness=burstiness,
        info_density=info_density,
        cliche_count=cliche_count,
        token_count=len(tokens),
    )


def should_quarantine_slop(slop_probability: float, domain_mode: str = "") -> bool:
    """Hard rule: slop > 0.65 AND domain != COGNITIVE_WARFARE_STUDY → quarantine."""
    if slop_probability > 0.65 and domain_mode != "COGNITIVE_WARFARE_STUDY":
        return True
    return False


def metrics_to_attack_index(
    slop_result: SlopClassifierResult,
    admiralty_reliability: AdmiraltyReliability = AdmiraltyReliability.F,
    credibility_rank: int = 6,
) -> JEVAttackIndexMetrics:
    return JEVAttackIndexMetrics(
        emotional_intensity=slop_result.burstiness,
        manipulative_markers=[],
        slop_probability=slop_result.slop_probability,
        admiralty_reliability=admiralty_reliability,
        credibility_rank=credibility_rank,
    )
