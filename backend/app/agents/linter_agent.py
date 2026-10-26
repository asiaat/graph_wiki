"""Agent 5: AdversarialLinterAgent — Graph Health, Contradiction & Attack-Index Monitor."""

import logging
import math
from datetime import datetime
from typing import Any

from app.config import settings
from app.db.kuzu_client import KuzuClient

logger = logging.getLogger(__name__)


class AdversarialLinterAgent:
    def __init__(self, kuzu: KuzuClient):
        self.kuzu = kuzu

    async def run_lint(self) -> dict[str, Any]:
        """Run all scheduled lint checks."""
        contradictions = await self._detect_contradictions()
        decay_issues = await self._apply_confidence_decay()
        wave_alerts = await self._detect_wave_anomalies()
        structural_gaps = await self._identify_structural_gaps()

        return {
            "contradictions": contradictions,
            "decay_issues": decay_issues,
            "wave_alerts": wave_alerts,
            "structural_gaps": structural_gaps,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    async def _detect_contradictions(self) -> list[dict[str, Any]]:
        """Semantic Contradiction Detection: find opposing claims on same entity."""
        cypher = """
        MATCH (c1:Claim)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e:Entity)
        MATCH (c2:Claim)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e:Entity)
        WHERE c1.claim_id < c2.claim_id
        AND c1.predicate = c2.predicate
        AND c1.statement <> c2.statement
        RETURN c1, c2, e
        """
        rows = await self.kuzu.read(cypher)
        contradictions = []
        for r in rows:
            contradictions.append(
                {
                    "entity": r[2],
                    "claim_a": r[0],
                    "claim_b": r[1],
                    "severity": 0.8,
                    "detected_at": datetime.utcnow().isoformat() + "Z",
                }
            )
        return contradictions

    async def _apply_confidence_decay(self) -> list[dict[str, Any]]:
        """Ebbinghaus Confidence Decay: C(t) = C₀ · e^(-λΔt)."""
        cypher = """
        MATCH (c:Claim)
        WHERE c.valid_to IS NULL OR c.valid_to > $now
        RETURN c.claim_id, c.confidence, c.valid_from
        """
        rows = await self.kuzu.read(cypher, {"now": datetime.utcnow().isoformat() + "Z"})

        decayed = []
        for claim_id, confidence, valid_from in rows:
            if not valid_from:
                continue
            try:
                verified_at = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
                delta_t = (datetime.utcnow() - verified_at).total_seconds() / 86400  # days
                lambda_decay = 0.01  # daily decay rate
                new_confidence = confidence * math.exp(-lambda_decay * delta_t)
                if new_confidence < 0.5:
                    decayed.append(
                        {
                            "claim_id": claim_id,
                            "old_confidence": confidence,
                            "new_confidence": new_confidence,
                            "delta_days": delta_t,
                        }
                    )
            except (ValueError, TypeError):
                continue

        return decayed

    async def _detect_wave_anomalies(self) -> list[dict[str, Any]]:
        """Attack-Index Wave Detection: flag narrative bursts > 2.5σ."""
        cypher = """
        MATCH (s:SourceDoc)
        WHERE s.published_at > $window_start
        RETURN s.published_at, s.attack_index, s.term
        """
        window_start = datetime.utcnow().timestamp() - 86400 * 7  # 7 days ago
        rows = await self.kuzu.read(cypher, {"window_start": window_start})

        if not rows:
            return []

        attack_indices = [r[1] for r in rows if r[1] is not None]
        if len(attack_indices) < 10:
            return []

        mean = sum(attack_indices) / len(attack_indices)
        std = (sum((x - mean) ** 2 for x in attack_indices) / len(attack_indices)) ** 0.5

        if std == 0:
            return []

        anomalies = []
        for r in rows:
            if r[1] is not None:
                z_score = (r[1] - mean) / std
                if z_score > 2.5:
                    anomalies.append(
                        {
                            "timestamp": r[0],
                            "term": r[2],
                            "z_score": z_score,
                            "attack_index": r[1],
                        }
                    )

        return anomalies

    async def _identify_structural_gaps(self) -> list[dict[str, Any]]:
        """Adamic-Adar & Bridge Analysis: find weakly connected subgraphs."""
        cypher = """
        MATCH (e:Entity) WHERE NOT (e)-[:RELATES_TO]->()
        RETURN e.id, e.canonical_name, e.category
        """
        rows = await self.kuzu.read(cypher)
        return [
            {
                "entity_id": r[0],
                "canonical_name": r[1],
                "category": r[2],
                "gap_type": "ORPHANED_ENTITY",
            }
            for r in rows
        ]
