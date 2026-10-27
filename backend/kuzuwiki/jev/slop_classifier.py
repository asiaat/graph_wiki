"""Deterministic synthetic slop classifier.

Three stylometric signals, computed the way the literature defines them:

* **Perplexity** - Shannon entropy over the unigram distribution,
  ``2 ** H``. Low entropy means repetitive, template-like text.
* **Burstiness** - standard deviation of *sentence lengths*. Machine prose
  has flat sentence lengths; human prose alternates.
* **Information density** - atomic claims per token, where an atomic claim is
  a sentence carrying an attribution or a number.

None of these alone proves slop, so the score is a weighted blend and the
decision is a threshold in :func:`should_quarantine_slop`.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from pydantic import BaseModel

from kuzuwiki.jev.schemas import AdmiraltyReliability, JEVAttackIndexMetrics

#: Transitional clichés typical of generated filler prose.
SLOP_CLICHES = (
    "in today's fast-paced world",
    "in today's rapidly evolving",
    "the rise of",
    "a game changer",
    "testament to",
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
    "unlock",
    "landscape",
    "revolutionize",
)

#: Phrases that attribute a statement to a source (raises information density).
ATTRIBUTION_MARKERS = (
    "according to",
    "told",
    "said",
    "stated",
    "reported",
    "confirmed",
    "announced",
    "published",
    "found",
    "showed",
    "data",
    "record",
    "registry",
    "filing",
    "court",
    "sanctions list",
)

_TOKEN_RE = re.compile(r"[^\s]+")
_SENTENCE_RE = re.compile(r"[.!?]+")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


class SlopClassifierResult(BaseModel):
    slop_probability: float
    perplexity: float
    burstiness: float
    info_density: float
    cliche_count: int
    token_count: int
    sentence_count: int = 0
    attribution_count: int = 0


def _tokenize(text: str) -> list[str]:
    return [t.strip(".,!?;:\"'()[]{}").lower() for t in _TOKEN_RE.findall(text) if t.strip()]


def _compute_perplexity(tokens: list[str]) -> float:
    """Shannon-entropy perplexity over the unigram distribution."""
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
    return 2**entropy


def _compute_burstiness(text: str) -> float:
    """Standard deviation of sentence lengths (the standard burstiness proxy)."""
    sentences = [s for s in _SENTENCE_RE.split(text) if s.strip()]
    if len(sentences) < 2:
        return 0.0
    lengths = [len(_tokenize(s)) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((n - mean) ** 2 for n in lengths) / len(lengths)
    return math.sqrt(variance)


def _compute_info_density(text: str, tokens: list[str]) -> tuple[float, int, int]:
    """Atomic claims per token. Returns (density, claim_count, attribution_count)."""
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    if not sentences:
        return 0.0, 0, 0
    lowered = text.lower()
    attribution_count = sum(1 for m in ATTRIBUTION_MARKERS if m in lowered)
    atomic_claims = 0
    for sentence in sentences:
        has_attribution = any(m in sentence.lower() for m in ATTRIBUTION_MARKERS)
        has_number = bool(_NUMBER_RE.search(sentence))
        has_proper_noun = bool(re.search(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+)*", sentence))
        if has_attribution or has_number or has_proper_noun:
            atomic_claims += 1
    return atomic_claims / max(len(tokens), 1), atomic_claims, attribution_count


def _count_cliches(text: str) -> int:
    lowered = text.lower()
    return sum(1 for c in SLOP_CLICHES if c in lowered)


def classify_slop(text: str, admiralty_reliability: str | None = None) -> SlopClassifierResult:
    """Score ``text`` on a ``[0, 1]`` synthetic-slop scale.

    ``admiralty_reliability`` is accepted for backwards compatibility but is
    deliberately *not* mixed into the score: slop is a property of the prose,
    and source reliability is a separate axis combined later in
    :func:`metrics_to_attack_index`.
    """
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
    burstiness = _compute_burstiness(text)
    info_density, _claims, attributions = _compute_info_density(text, tokens)
    cliche_count = _count_cliches(text)

    # Low information density and flat sentence rhythm indicate generated text.
    density_penalty = max(0.0, 1.0 - min(1.0, info_density * 8.0)) * 0.45
    cliche_penalty = min(1.0, cliche_count / 6.0) * 0.30
    # Very low perplexity == highly repetitive == templated.
    repetition_penalty = max(0.0, 1.0 - min(1.0, perplexity / 8.0)) * 0.25

    slop_probability = density_penalty + cliche_penalty + repetition_penalty
    slop_probability = min(1.0, max(0.0, slop_probability))

    return SlopClassifierResult(
        slop_probability=slop_probability,
        perplexity=perplexity,
        burstiness=burstiness,
        info_density=info_density,
        cliche_count=cliche_count,
        token_count=len(tokens),
        sentence_count=len([s for s in _SENTENCE_RE.split(text) if s.strip()]),
        attribution_count=attributions,
    )


def should_quarantine_slop(slop_probability: float, domain_mode: str = "") -> bool:
    """Hard rule: slop > 0.65 AND domain mode is not cognitive-warfare study.

    Cognitive-warfare research deliberately ingests manipulative material, so
    that domain mode is exempt from the quarantine rule.
    """
    if domain_mode.strip().upper() == "COGNITIVE_WARFARE_STUDY":
        return False
    return slop_probability > 0.65


def metrics_to_attack_index(
    slop_result: SlopClassifierResult,
    admiralty_reliability: AdmiraltyReliability = AdmiraltyReliability.F,
    credibility_rank: int = 6,
    manipulative_markers: list[str] | None = None,
) -> JEVAttackIndexMetrics:
    """Fold slop metrics and source reliability into the Attack-Index vector."""
    return JEVAttackIndexMetrics(
        emotional_intensity=min(1.0, slop_result.burstiness / 25.0),
        manipulative_markers=manipulative_markers or [],
        slop_probability=slop_result.slop_probability,
        admiralty_reliability=admiralty_reliability,
        credibility_rank=credibility_rank,
    )
