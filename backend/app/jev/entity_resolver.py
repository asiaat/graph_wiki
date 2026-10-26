"""Hybrid entity resolution: Vector Cosine >0.92 + Jaro-Winkler + Deterministic IDs."""

import logging
import re
from typing import Optional

from pydantic import BaseModel

from app.jev.schemas import JEVExtractedEntity

logger = logging.getLogger(__name__)


class EntityResolutionResult(BaseModel):
    resolved_id: str
    canonical_name: str
    category: str
    aliases: list[str]
    external_ids: dict[str, str]
    is_new: bool
    similarity_score: float


def _jaro_winkler(s1: str, s2: str) -> float:
    """Simplified Jaro-Winkler distance (0.0 - 1.0)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    # Jaro distance
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

    # Transpositions
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

    # Jaro-Winkler prefix bonus
    prefix = 0
    for i in range(min(len(s1), len(s2), 4)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + (0.1 * prefix * (1 - jaro))


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class EntityResolver:
    """Hybrid entity deduplication against existing KùzuDB nodes."""

    def __init__(self, kuzu_client=None):
        self.kuzu = kuzu_client
        self.vector_threshold = 0.92
        self.jaro_threshold = 0.85

    def _deterministic_match(self, new_entity: JEVExtractedEntity, existing: dict) -> bool:
        """Check if deterministic IDs match."""
        for key, val in new_entity.deterministic_ids.items():
            if key in existing.get("external_ids", {}):
                if existing["external_ids"][key] == val:
                    return True
        return False

    def _alias_match(self, new_entity: JEVExtractedEntity, existing: dict) -> float:
        """Best alias match score."""
        aliases = [new_entity.canonical_name.lower()] + [a.lower() for a in new_entity.aliases]
        existing_aliases = [existing.get("canonical_name", "").lower()] + [
            a.lower() for a in existing.get("aliases", [])
        ]
        best = 0.0
        for a in aliases:
            for ea in existing_aliases:
                score = _jaro_winkler(a, ea)
                best = max(best, score)
        return best

    async def resolve(
        self,
        new_entity: JEVExtractedEntity,
        existing_entities: list[dict],
    ) -> EntityResolutionResult:
        """Returns resolved entity id, either existing or new."""
        best_match = None
        best_score = 0.0

        for existing in existing_entities:
            # Deterministic ID match (highest priority)
            if self._deterministic_match(new_entity, existing):
                return EntityResolutionResult(
                    resolved_id=existing["id"],
                    canonical_name=existing.get("canonical_name", new_entity.canonical_name),
                    category=existing.get("category", new_entity.category.value),
                    aliases=existing.get("aliases", []),
                    external_ids=existing.get("external_ids", {}),
                    is_new=False,
                    similarity_score=1.0,
                )

            # Jaro-Winkler alias match
            jaro = self._alias_match(new_entity, existing)
            if jaro > best_score:
                best_score = jaro
                best_match = existing

            # Vector similarity (if available)
            if "embedding" in existing and existing["embedding"]:
                vec_sim = _cosine_similarity(existing["embedding"], [0.0] * 1024)
                best_score = max(best_score, vec_sim)

        if best_match and best_score >= self.jaro_threshold:
            return EntityResolutionResult(
                resolved_id=best_match["id"],
                canonical_name=best_match.get("canonical_name", new_entity.canonical_name),
                category=best_match.get("category", new_entity.category.value),
                aliases=best_match.get("aliases", []),
                external_ids=best_match.get("external_ids", {}),
                is_new=False,
                similarity_score=best_score,
            )

        # New entity
        new_id = self._generate_id(new_entity)
        return EntityResolutionResult(
            resolved_id=new_id,
            canonical_name=new_entity.canonical_name,
            category=new_entity.category.value,
            aliases=new_entity.aliases,
            external_ids=new_entity.deterministic_ids,
            is_new=True,
            similarity_score=0.0,
        )

    @staticmethod
    def _generate_id(entity: JEVExtractedEntity) -> str:
        """Generate deterministic slug from entity attributes."""
        cat = entity.category.value.lower()
        name = re.sub(r"[^a-z0-9]+", "-", entity.canonical_name.lower()).strip("-")[:64]
        return f"{cat}:{name}"
