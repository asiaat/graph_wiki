"""Agent 4: GraphWikiCompilerAgent — KùzuDB upsert & wiki maintainer.

Integrates verified JEV triples into KùzuDB and compiles the human-readable
Markdown dossiers.

The invariant this agent exists to guarantee: **every claim carries its
provenance**. A claim is only ever linked to the document it was extracted
from through an ``EVIDENCED_BY`` edge carrying the exact quote and its
character offsets, and both parties of a relation are linked to the entities
they concern through resolved *ids* - not names.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.wiki_sync import WikiSync
from kuzuwiki.jev.entity_resolver import EntityResolutionResult, EntityResolver
from kuzuwiki.jev.schemas import (
    JEVDistillationBundle,
    JEVExtractedRelation,
)

logger = logging.getLogger(__name__)


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware datetime for a TIMESTAMP column."""
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class GraphWikiCompilerAgent:
    def __init__(self, kuzu: KuzuClient, wiki_vault_path: str = "/data/wiki"):
        self.kuzu = kuzu
        self.wiki_sync = WikiSync(kuzu, wiki_vault_path)
        self.resolver = EntityResolver(kuzu)

    async def compile_bundle(self, bundle: JEVDistillationBundle) -> dict[str, int]:
        """Upsert all entities, relations and claims from a distillation bundle."""
        stats = {
            "entities": 0,
            "relations": 0,
            "claims": 0,
            "provenance_edges": 0,
            "terms": 0,
            "term_edges": 0,
        }

        existing_entities = await self._fetch_existing_entities()

        resolved_entities: list[EntityResolutionResult] = []
        for entity in bundle.entities:
            resolved = await self.resolver.resolve(entity, existing_entities)
            resolved_entities.append(resolved)
            if resolved.is_new:
                stats["entities"] += 1

        # Name -> id map so relations can be wired to the right nodes.
        id_by_name: dict[str, str] = {}
        for resolved in resolved_entities:
            id_by_name[resolved.canonical_name.lower()] = resolved.resolved_id
            for alias in resolved.aliases:
                id_by_name.setdefault(alias.lower(), resolved.resolved_id)

        for resolved in resolved_entities:
            await self.wiki_sync.upsert_entity(
                {
                    "id": resolved.resolved_id,
                    "canonical_name": resolved.canonical_name,
                    "category": resolved.category,
                    "aliases": resolved.aliases,
                    "external_ids": resolved.external_ids,
                    "summary": resolved.summary_fact,
                    "wiki_markdown": "",
                    "confidence_score": resolved.confidence,
                    "lifecycle_state": self._lifecycle_state(resolved),
                    "hvg_centrality": 0.0,
                }
            )

        for relation in bundle.relations:
            source_id = id_by_name.get(relation.source_entity.lower())
            target_id = id_by_name.get(relation.target_entity.lower())
            if not source_id or not target_id:
                logger.warning(
                    "Skipping relation %s -> %s: entities not resolved",
                    relation.source_entity,
                    relation.target_entity,
                )
                continue

            claim_id = self._claim_id(source_id, relation, target_id)
            await self._insert_relation(relation, source_id, target_id, claim_id)
            stats["relations"] += 1

            await self._create_claim_node(relation, claim_id, source_id, target_id)
            stats["claims"] += 1

            wrote = await self._write_provenance(relation, claim_id, bundle.doc_sha256)
            stats["provenance_edges"] += 1 if wrote else 0

        await self.wiki_sync.sync_all_entities()
        stats.update(await self.persist_term_hierarchy(bundle))
        return stats

    async def persist_term_hierarchy(self, bundle: JEVDistillationBundle) -> dict[str, int]:
        """Persist the Lande visibility graph as the DomainTerm hierarchy.

        The hierarchy used to be computed and then thrown away; without it the
        "natural term hierarchy" of AGENTS.md never reached the graph.
        """
        stats = {"terms": 0, "term_edges": 0}
        weights = bundle.term_weights or {}
        bursts = set(bundle.burst_terms or [])
        degrees: dict[str, int] = {}
        for edge in bundle.hvg_edges or []:
            degrees[edge["term_a"]] = degrees.get(edge["term_a"], 0) + 1
            degrees[edge["term_b"]] = degrees.get(edge["term_b"], 0) + 1

        for term, weight in weights.items():
            try:
                await self.kuzu.write(
                    """
                    MERGE (t:DomainTerm {term: $term})
                    SET t.idf_weight = $idf_weight,
                        t.hvg_degree = $hvg_degree,
                        t.burst_score = $burst_score
                    """,
                    {
                        "term": term,
                        "idf_weight": float(weight),
                        "hvg_degree": int(degrees.get(term, 0)),
                        "burst_score": 1.0 if term in bursts else 0.0,
                    },
                )
                stats["terms"] += 1
            except Exception as exc:
                logger.error("Could not persist DomainTerm %s: %s", term, exc)

        for edge in bundle.hvg_edges or []:
            direction = edge.get("direction", "")
            if direction == "undirected" or "->" not in direction:
                continue
            source, target = direction.split("->", 1)
            try:
                await self.kuzu.write(
                    """
                    MERGE (a:DomainTerm {term: $source})
                    MERGE (b:DomainTerm {term: $target})
                    MERGE (a)-[r:TERM_DOMINATES]->(b)
                    SET r.visibility_weight = $weight,
                        r.directional_asymmetry = $asymmetry
                    """,
                    {
                        "source": source,
                        "target": target,
                        "weight": float(edge.get("visibility_weight", 0.0)),
                        "asymmetry": float(edge.get("visibility_weight", 0.0)),
                    },
                )
                stats["term_edges"] += 1
            except Exception as exc:
                logger.debug("Could not persist TERM_DOMINATES edge: %s", exc)

        return stats

    @staticmethod
    def _lifecycle_state(resolved: EntityResolutionResult) -> str:
        """Lifecycle reflects evidence quality - never a hardcoded VERIFIED."""
        if resolved.is_new:
            return "UNVERIFIED"
        if resolved.confidence >= 0.8:
            return "CORROBORATED"
        if resolved.confidence >= 0.5:
            return "SINGLE_SOURCE"
        return "DISPUTED"

    @staticmethod
    def _claim_id(source_id: str, relation: JEVExtractedRelation, target_id: str) -> str:
        """Stable claim identity derived from the triple itself."""
        digest = hashlib.sha256(
            f"{source_id}|{relation.relation_type.value}|{target_id}".encode()
        ).hexdigest()[:16]
        return f"claim-{digest}"

    async def _fetch_existing_entities(self) -> list[dict[str, Any]]:
        rows = await self.kuzu.read(
            "MATCH (e:Entity) RETURN e.id AS id, e.canonical_name AS canonical_name, "
            "e.category AS category, e.aliases AS aliases, e.external_ids AS external_ids, "
            "e.summary AS summary, e.confidence_score AS confidence_score"
        )
        return list(rows)

    async def _insert_relation(
        self,
        relation: JEVExtractedRelation,
        source_id: str,
        target_id: str,
        claim_id: str,
    ) -> None:
        await self.kuzu.write(
            """
            MERGE (src:Entity {id: $source_id})
            MERGE (tgt:Entity {id: $target_id})
            MERGE (src)-[rel:RELATES_TO {relation_type: $rel_type}]->(tgt)
            ON CREATE SET
                rel.weight = $weight,
                rel.valid_from = $valid_from,
                rel.valid_to = $valid_to,
                rel.claim_id = $claim_id,
                rel.is_disputed = $is_disputed
            ON MATCH SET
                rel.weight = $weight,
                rel.valid_from = $valid_from,
                rel.valid_to = $valid_to,
                rel.claim_id = $claim_id,
                rel.is_disputed = $is_disputed
            """,
            {
                "source_id": source_id,
                "target_id": target_id,
                "rel_type": relation.relation_type.value,
                "weight": relation.weight,
                "valid_from": _parse_timestamp(relation.temporal_valid_from),
                "valid_to": _parse_timestamp(relation.temporal_valid_to),
                "claim_id": claim_id,
                "is_disputed": False,
            },
        )

    async def _create_claim_node(
        self,
        relation: JEVExtractedRelation,
        claim_id: str,
        source_id: str,
        target_id: str,
    ) -> None:
        await self.kuzu.write(
            """
            MERGE (c:Claim {claim_id: $claim_id})
            ON CREATE SET
                c.statement = $statement,
                c.predicate = $predicate,
                c.valid_from = $valid_from,
                c.valid_to = $valid_to,
                c.confidence = $confidence,
                c.nli_entailment = $nli_entailment,
                c.swarm_votes = $swarm_votes,
                c.status = $status
            ON MATCH SET
                c.statement = $statement,
                c.predicate = $predicate,
                c.valid_from = $valid_from,
                c.valid_to = $valid_to,
                c.confidence = $confidence,
                c.nli_entailment = $nli_entailment,
                c.swarm_votes = $swarm_votes,
                c.status = $status
            """,
            {
                "claim_id": claim_id,
                "statement": (
                    f"{relation.source_entity} {relation.relation_type.value} "
                    f"{relation.target_entity}"
                ),
                "predicate": relation.relation_type.value,
                "valid_from": _parse_timestamp(relation.temporal_valid_from),
                "valid_to": _parse_timestamp(relation.temporal_valid_to),
                "confidence": relation.weight,
                "nli_entailment": relation.nli_entailment_score,
                "swarm_votes": relation.swarm_consensus_count,
                "status": "CORROBORATED"
                if relation.swarm_consensus_count >= 2
                else "SINGLE_SOURCE",
            },
        )

        # Link the claim to both entities by their resolved ids.
        await self.kuzu.write(
            "MATCH (c:Claim {claim_id: $claim_id}) MATCH (e:Entity {id: $source_id}) "
            "MERGE (c)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e)",
            {"claim_id": claim_id, "source_id": source_id},
        )
        await self.kuzu.write(
            "MATCH (c:Claim {claim_id: $claim_id}) MATCH (e:Entity {id: $target_id}) "
            "MERGE (c)-[:ASSERTS_ABOUT {role: 'OBJECT'}]->(e)",
            {"claim_id": claim_id, "target_id": target_id},
        )

    async def _write_provenance(
        self,
        relation: JEVExtractedRelation,
        claim_id: str,
        doc_sha256: str,
    ) -> bool:
        """Link the claim to its source document with the exact quote."""
        evidence = relation.evidence
        try:
            await self.kuzu.write(
                """
                MATCH (c:Claim {claim_id: $claim_id})
                MATCH (s:SourceDoc {sha256: $sha256})
                MERGE (c)-[e:EVIDENCED_BY]->(s)
                SET e.exact_quote = $exact_quote,
                    e.start_char = $start_char,
                    e.end_char = $end_char,
                    e.nli_score = $nli_score,
                    e.extracted_by_swarm_run = $swarm_run
                """,
                {
                    "claim_id": claim_id,
                    "sha256": doc_sha256,
                    "exact_quote": evidence.exact_quote,
                    "start_char": evidence.start_char,
                    "end_char": evidence.end_char,
                    "nli_score": relation.nli_entailment_score,
                    "swarm_run": f"swarm-{doc_sha256[:12]}",
                },
            )
            return True
        except Exception as exc:
            logger.error(
                "Could not write provenance for claim %s: %s (source doc %s may be missing)",
                claim_id,
                exc,
                doc_sha256,
            )
            return False

    async def entity_dossier(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch an entity with its claims, relations and provenance."""
        entity_rows = await self.kuzu.read(
            "MATCH (e:Entity {id: $id}) RETURN e.canonical_name AS canonical_name, "
            "e.category AS category, e.summary AS summary, e.slug AS slug",
            {"id": entity_id},
        )
        if not entity_rows:
            return None
        claims = await self.kuzu.read(
            """
            MATCH (c:Claim)-[:ASSERTS_ABOUT]->(e:Entity {id: $id})
            MATCH (c)-[ev:EVIDENCED_BY]->(s:SourceDoc)
            RETURN c.statement AS statement, c.nli_entailment AS nli_entailment,
                   c.swarm_votes AS swarm_votes, ev.exact_quote AS quote,
                   s.sha256 AS source_sha256
            """,
            {"id": entity_id},
        )
        relations = await self.kuzu.read(
            """
            MATCH (a:Entity {id: $id})-[r:RELATES_TO]->(b:Entity)
            RETURN b.canonical_name AS target, r.relation_type AS relation_type,
                   r.weight AS weight
            """,
            {"id": entity_id},
        )
        return {
            "id": entity_id,
            **entity_rows[0],
            "claims": claims,
            "relations": relations,
        }
