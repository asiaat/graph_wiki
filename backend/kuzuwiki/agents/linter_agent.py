"""Agent 5: AdversarialLinterAgent — graph health, contradiction & Attack-Index monitor.

Four scheduled checks:

1. **Semantic contradiction detection** - opposing claims about the same
   entity. Both claims are flagged with a ``[:CONTRADICTS {severity}]`` edge
   so the conflict is visible in the graph, not just in a report.
2. **Ebbinghaus confidence decay** - ``C(t) = C0 · e^(-λΔt)`` applied to
   dynamic claims that have not been re-verified. The decayed value is
   *persisted*; a decay that is only reported is a decay nobody acts on.
3. **Attack-Index wave detection** - frequency spikes beyond 2.5σ.
4. **Structural gap identification** - orphaned or uncorroborated entities,
   each of which becomes a ``ComplicationTicket`` for the OSINT agent.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from kuzuwiki.db.kuzu_client import KuzuClient

logger = logging.getLogger(__name__)

#: Daily decay rate for dynamic claims (AGENTS.md Agent 5).
LAMBDA_DECAY = 0.01

#: Wave detection threshold in standard deviations (AGENTS.md Agent 5).
WAVE_SIGMA = 2.5

#: Minimum sample size before wave detection is meaningful.
MIN_WAVE_SAMPLES = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
            "timestamp": _utcnow().isoformat(),
        }

    async def _detect_contradictions(self) -> list[dict[str, Any]]:
        """Find opposing claims about the same entity and flag them."""
        rows = await self.kuzu.read(
            """
            MATCH (c1:Claim)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e:Entity)
            MATCH (c2:Claim)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e:Entity)
            WHERE c1.claim_id < c2.claim_id
              AND c1.predicate = c2.predicate
              AND c1.statement <> c2.statement
            RETURN c1.claim_id AS claim_a, c1.statement AS statement_a,
                   c2.claim_id AS claim_b, c2.statement AS statement_b,
                   e.id AS entity_id, e.canonical_name AS entity_name
            """
        )

        contradictions: list[dict[str, Any]] = []
        for row in rows:
            severity = self._severity(row.get("statement_a", ""), row.get("statement_b", ""))
            detected_at = _utcnow()
            try:
                await self.kuzu.write(
                    """
                    MATCH (a:Claim {claim_id: $claim_a})
                    MATCH (b:Claim {claim_id: $claim_b})
                    MERGE (a)-[r:CONTRADICTS]->(b)
                    SET r.contradiction_type = $ctype,
                        r.severity = $severity,
                        r.detected_at = $detected_at
                    """,
                    {
                        "claim_a": row["claim_a"],
                        "claim_b": row["claim_b"],
                        "ctype": "OPPOSING_CLAIM",
                        "severity": severity,
                        "detected_at": detected_at,
                    },
                )
            except Exception as exc:
                logger.error("Could not write CONTRADICTS edge: %s", exc)

            contradictions.append(
                {
                    "entity_id": row.get("entity_id"),
                    "entity_name": row.get("entity_name"),
                    "claim_a": row.get("claim_a"),
                    "claim_b": row.get("claim_b"),
                    "statement_a": row.get("statement_a"),
                    "statement_b": row.get("statement_b"),
                    "severity": severity,
                    "detected_at": detected_at.isoformat(),
                }
            )
        return contradictions

    @staticmethod
    def _severity(statement_a: str, statement_b: str) -> float:
        """Higher severity when the two statements assert incompatible things."""
        a = (statement_a or "").lower()
        b = (statement_b or "").lower()
        negation_markers = ("not ", "never ", "no evidence", "denied", "denies", "rejects")
        contradictory = any(m in a for m in negation_markers) != any(
            m in b for m in negation_markers
        )
        return 0.9 if contradictory else 0.6

    async def _apply_confidence_decay(self) -> list[dict[str, Any]]:
        """Apply Ebbinghaus decay and persist the new confidence."""
        rows = await self.kuzu.read(
            """
            MATCH (c:Claim)
            WHERE c.valid_to IS NULL OR c.valid_to > $now
            RETURN c.claim_id AS claim_id, c.confidence AS confidence,
                   c.valid_from AS valid_from, c.swarm_votes AS swarm_votes
            """,
            {"now": _utcnow()},
        )

        decayed: list[dict[str, Any]] = []
        now = _utcnow()
        for row in rows:
            verified_at = row.get("valid_from")
            confidence = row.get("confidence")
            if not verified_at or confidence is None:
                continue
            if isinstance(verified_at, str):
                try:
                    verified_at = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
                except ValueError:
                    continue
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            delta_days = max(0.0, (now - verified_at).total_seconds() / 86400)
            new_confidence = confidence * math.exp(-LAMBDA_DECAY * delta_days)
            if new_confidence >= 0.5:
                continue

            try:
                await self.kuzu.write(
                    "MATCH (c:Claim {claim_id: $claim_id}) SET c.confidence = $confidence",
                    {"claim_id": row["claim_id"], "confidence": new_confidence},
                )
            except Exception as exc:
                logger.error("Could not persist decayed confidence: %s", exc)

            decayed.append(
                {
                    "claim_id": row["claim_id"],
                    "old_confidence": confidence,
                    "new_confidence": new_confidence,
                    "delta_days": delta_days,
                }
            )
        return decayed

    async def _detect_wave_anomalies(self) -> list[dict[str, Any]]:
        """Flag narrative bursts beyond 2.5 sigma above the baseline."""
        window_start = _utcnow() - timedelta(days=7)
        rows = await self.kuzu.read(
            """
            MATCH (s:SourceDoc)
            WHERE s.published_at IS NOT NULL AND s.published_at > $window_start
            RETURN s.published_at AS published_at, s.attack_index AS attack_index,
                   s.primary_term AS primary_term, s.sha256 AS sha256
            """,
            {"window_start": window_start},
        )

        values = [r["attack_index"] for r in rows if r.get("attack_index") is not None]
        if len(values) < MIN_WAVE_SAMPLES:
            return []

        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        if std == 0:
            return []

        anomalies: list[dict[str, Any]] = []
        for row in rows:
            index = row.get("attack_index")
            if index is None:
                continue
            z_score = (index - mean) / std
            if z_score <= WAVE_SIGMA:
                continue
            published_at = row.get("published_at")
            anomalies.append(
                {
                    "timestamp": published_at.isoformat()
                    if hasattr(published_at, "isoformat")
                    else published_at,
                    "term": row.get("primary_term"),
                    "sha256": row.get("sha256"),
                    "z_score": round(z_score, 3),
                    "attack_index": index,
                }
            )
        return anomalies

    async def _identify_structural_gaps(self) -> list[dict[str, Any]]:
        """Find orphaned / uncorroborated entities and open a ticket for each."""
        rows = await self.kuzu.read(
            """
            MATCH (e:Entity)
            WHERE NOT (e)-[:RELATES_TO]->() AND NOT (e)<-[:ASSERTS_ABOUT]-()
            RETURN e.id AS entity_id, e.canonical_name AS canonical_name,
                   e.category AS category
            """
        )

        gaps: list[dict[str, Any]] = []
        for row in rows:
            gap = {
                "entity_id": row["entity_id"],
                "canonical_name": row["canonical_name"],
                "category": row["category"],
                "gap_type": "ORPHANED_ENTITY",
            }
            await self._open_ticket(row["entity_id"], "ORPHANED_ENTITY", gap)
            gaps.append(gap)
        return gaps

    async def _open_ticket(self, entity_id: str, gap_type: str, detail: dict[str, Any]) -> None:
        """Record a ComplicationTicket so the OSINT agent can pick the gap up."""
        import hashlib

        ticket_id = "ticket-" + hashlib.sha256(f"{entity_id}|{gap_type}".encode()).hexdigest()[:12]
        try:
            await self.kuzu.write(
                """
                MERGE (t:ComplicationTicket {ticket_id: $ticket_id})
                ON CREATE SET t.target_entity_id = $entity_id,
                              t.gap_type = $gap_type,
                              t.hypothesis_query = $hypothesis,
                              t.generated_dorks = $dorks,
                              t.status = 'OPEN',
                              t.created_at = $created_at
                """,
                {
                    "ticket_id": ticket_id,
                    "entity_id": entity_id,
                    "gap_type": gap_type,
                    "hypothesis": (
                        f"Identify corroborating primary evidence for "
                        f"{detail.get('canonical_name', entity_id)}"
                    ),
                    "dorks": [],
                    "created_at": _utcnow(),
                },
            )
        except Exception as exc:
            logger.error("Could not open ComplicationTicket for %s: %s", entity_id, exc)
