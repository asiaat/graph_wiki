"""Hybrid entity resolution: deterministic IDs + Jaro-Winkler aliases + optional vectors.

Resolution order (highest confidence first):

1. **Deterministic identifiers** - a shared IMO / tax id / registration number
   is decisive regardless of naming.
2. **Vector cosine similarity** - only used when a real embedding exists on
   both sides; the ``> 0.92`` threshold from AGENTS.md applies *here only*.
3. **Jaro-Winkler over canonical names and aliases** - the always-available
   fallback, compared against its own threshold.

The two similarity scales are never mixed: an earlier version compared a
cosine score against the Jaro threshold, which could never work.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from kuzuwiki.jev.schemas import JEVExtractedEntity

logger = logging.getLogger(__name__)


class EntityResolutionResult(BaseModel):
    resolved_id: str
    canonical_name: str
    category: str
    aliases: list[str]
    external_ids: dict[str, str]
    is_new: bool
    similarity_score: float
    summary_fact: str = ""
    confidence: float = 0.5
    match_strategy: str = "new"


def _jaro_winkler(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity (0.0 - 1.0)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    match_distance = max(len(s1), len(s2)) // 2 - 1
    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0

    for i in range(len(s1)):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len(s1)):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        (matches / len(s1)) + (matches / len(s2)) + ((matches - transpositions / 2) / matches)
    ) / 3.0

    prefix = 0
    for i in range(min(len(s1), len(s2), 4)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + (0.1 * prefix * (1 - jaro))


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _coerce_external_ids(value: Any) -> dict[str, str]:
    """External ids arrive as JSON text (the graph column is JSON typed)."""
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            return {}
    return {}


class EntityResolver:
    """Hybrid entity deduplication against existing KùzuDB nodes."""

    def __init__(
        self,
        kuzu_client=None,
        vector_threshold: float = 0.92,
        jaro_threshold: float = 0.85,
    ):
        self.kuzu = kuzu_client
        self.vector_threshold = vector_threshold
        self.jaro_threshold = jaro_threshold

    @staticmethod
    def _deterministic_match(new_entity: JEVExtractedEntity, existing: dict) -> bool:
        """True when a deterministic identifier matches exactly."""
        existing_ids = _coerce_external_ids(existing.get("external_ids"))
        for key, val in new_entity.deterministic_ids.items():
            if existing_ids.get(key) == val:
                return True
        return False

    @staticmethod
    def _alias_match(new_entity: JEVExtractedEntity, existing: dict) -> float:
        """Best similarity between any name variant on either side."""
        aliases = [new_entity.canonical_name.lower(), *[a.lower() for a in new_entity.aliases]]
        existing_aliases = [
            str(existing.get("canonical_name", "")).lower(),
            *[str(a).lower() for a in existing.get("aliases", []) or []],
        ]
        best = 0.0
        for a in aliases:
            for ea in existing_aliases:
                if not a or not ea:
                    continue
                best = max(best, _jaro_winkler(a, ea))
        return best

    async def resolve(
        self,
        new_entity: JEVExtractedEntity,
        existing_entities: list[dict],
        embedding: list[float] | None = None,
    ) -> EntityResolutionResult:
        """Resolve an extracted entity against the graph."""
        best_jaro_match: dict | None = None
        best_jaro = 0.0
        best_vector_match: dict | None = None
        best_vector = 0.0

        for existing in existing_entities:
            if self._deterministic_match(new_entity, existing):
                return self._to_result(
                    existing,
                    new_entity,
                    is_new=False,
                    score=1.0,
                    strategy="deterministic_id",
                )

            jaro = self._alias_match(new_entity, existing)
            if jaro > best_jaro:
                best_jaro = jaro
                best_jaro_match = existing

            if embedding is not None and existing.get("embedding"):
                vec_sim = _cosine_similarity(embedding, list(existing["embedding"]))
                if vec_sim > best_vector:
                    best_vector = vec_sim
                    best_vector_match = existing

        if best_vector_match is not None and best_vector >= self.vector_threshold:
            return self._to_result(
                best_vector_match,
                new_entity,
                is_new=False,
                score=best_vector,
                strategy="vector_cosine",
            )

        if best_jaro_match is not None and best_jaro >= self.jaro_threshold:
            return self._to_result(
                best_jaro_match,
                new_entity,
                is_new=False,
                score=best_jaro,
                strategy="jaro_winkler",
            )

        return EntityResolutionResult(
            resolved_id=self._generate_id(new_entity),
            canonical_name=new_entity.canonical_name,
            category=new_entity.category.value,
            aliases=list(new_entity.aliases),
            external_ids=dict(new_entity.deterministic_ids),
            is_new=True,
            similarity_score=0.0,
            summary_fact=new_entity.summary_fact,
            confidence=new_entity.confidence,
            match_strategy="new",
        )

    @staticmethod
    def _to_result(
        existing: dict,
        new_entity: JEVExtractedEntity,
        is_new: bool,
        score: float,
        strategy: str,
    ) -> EntityResolutionResult:
        """Merge the new extraction into the existing entity instead of dropping it."""
        existing_aliases = [str(a) for a in existing.get("aliases", []) or []]
        merged_aliases = list(
            dict.fromkeys([*existing_aliases, *new_entity.aliases, new_entity.canonical_name])
        )
        existing_ids = _coerce_external_ids(existing.get("external_ids"))
        merged_ids = {**existing_ids, **new_entity.deterministic_ids}
        existing_summary = str(existing.get("summary", "") or "")
        summary = existing_summary or new_entity.summary_fact
        existing_conf = float(existing.get("confidence_score", 0.0) or 0.0)

        return EntityResolutionResult(
            resolved_id=existing["id"],
            canonical_name=existing.get("canonical_name", new_entity.canonical_name),
            category=existing.get("category", new_entity.category.value),
            aliases=merged_aliases,
            external_ids=merged_ids,
            is_new=is_new,
            similarity_score=score,
            summary_fact=summary,
            confidence=max(existing_conf, new_entity.confidence),
            match_strategy=strategy,
        )

    @staticmethod
    def _generate_id(entity: JEVExtractedEntity) -> str:
        """Generate a deterministic slug from entity attributes."""
        cat = entity.category.value.lower()
        name = re.sub(r"[^a-z0-9]+", "-", entity.canonical_name.lower()).strip("-")[:64]
        return f"{cat}:{name}"
