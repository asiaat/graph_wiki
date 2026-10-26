"""Agent 4: GraphWikiCompilerAgent — KùzuDB Upsert & Wiki Maintainer.
Integrates verified JEV triples into KùzuDB and compiles Markdown wiki dossiers.
"""

import logging
from typing import Any

from app.config import settings
from app.db.kuzu_client import KuzuClient
from app.db.wiki_sync import WikiSync
from app.jev.entity_resolver import EntityResolver
from app.jev.schemas import JEVDistillationBundle, JEVExtractedEntity, JEVExtractedRelation

logger = logging.getLogger(__name__)


class GraphWikiCompilerAgent:
    def __init__(self, kuzu: KuzuClient, wiki_vault_path: str = "/data/wiki"):
        self.kuzu = kuzu
        self.wiki_sync = WikiSync(kuzu, wiki_vault_path)
        self.resolver = EntityResolver(kuzu)

    async def compile_bundle(self, bundle: JEVDistillationBundle) -> dict[str, int]:
        """Upsert all entities + relations from a distillation bundle."""
        stats = {"entities": 0, "relations": 0, "claims": 0}

        # Resolve entities against existing graph
        existing_entities = await self._fetch_existing_entities()

        resolved_entities = []
        for entity in bundle.entities:
            resolved = await self.resolver.resolve(entity, existing_entities)
            resolved_entities.append(resolved)
            if resolved.is_new:
                stats["entities"] += 1

        # Upsert entities + wiki files
        for resolved in resolved_entities:
            await self.wiki_sync.upsert_entity(
                {
                    "id": resolved.resolved_id,
                    "canonical_name": resolved.canonical_name,
                    "category": resolved.category,
                    "aliases": resolved.aliases,
                    "external_ids": resolved.external_ids,
                    "summary": "",
                    "wiki_markdown": "",
                    "confidence_score": 0.5,
                    "lifecycle_state": "VERIFIED",
                    "hvg_centrality": 0.0,
                }
            )

        # Insert relations as edges
        for relation in bundle.relations:
            await self._insert_relation(relation, resolved_entities)
            stats["relations"] += 1

        # Create Claim nodes for each relation
        for relation in bundle.relations:
            await self._create_claim_node(relation)
            stats["claims"] += 1

        return stats

    async def _fetch_existing_entities(self) -> list[dict[str, Any]]:
        rows = await self.kuzu.read(
            "MATCH (e:Entity) RETURN e.id, e.canonical_name, e.category, e.aliases, "
            "e.external_ids, e.wiki_markdown, e.confidence_score"
        )
        return [
            {
                "id": r[0],
                "canonical_name": r[1],
                "category": r[2],
                "aliases": r[3] or [],
                "external_ids": r[4] or {},
                "wiki_markdown": r[5] or "",
                "confidence_score": r[6] or 0.5,
            }
            for r in rows
        ]

    async def _insert_relation(
        self, relation: JEVExtractedRelation, resolved_entities: list[Any]
    ) -> None:
        source_id = next(
            (
                r.resolved_id
                for r in resolved_entities
                if r.canonical_name == relation.source_entity
            ),
            None,
        )
        target_id = next(
            (
                r.resolved_id
                for r in resolved_entities
                if r.canonical_name == relation.target_entity
            ),
            None,
        )

        if not source_id or not target_id:
            logger.warning("Skipping relation %s: entities not resolved", relation.relation_type)
            return

        cypher = """
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
        """
        params = {
            "source_id": source_id,
            "target_id": target_id,
            "rel_type": relation.relation_type.value,
            "weight": relation.nli_entailment_score,
            "valid_from": relation.temporal_valid_from,
            "valid_to": relation.temporal_valid_to,
            "claim_id": f"claim-{relation.source_entity}-{relation.target_entity}",
            "is_disputed": False,
        }
        await self.kuzu.enqueue_write(cypher, params)

    async def _create_claim_node(self, relation: JEVExtractedRelation) -> None:
        claim_id = f"claim-{relation.source_entity}-{relation.target_entity}"
        cypher = """
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
        """
        params = {
            "claim_id": claim_id,
            "statement": f"{relation.source_entity} {relation.relation_type.value} {relation.target_entity}",
            "predicate": relation.relation_type.value,
            "valid_from": relation.temporal_valid_from,
            "valid_to": relation.temporal_valid_to,
            "confidence": relation.nli_entailment_score,
            "nli_entailment": relation.nli_entailment_score,
            "swarm_votes": relation.swarm_consensus_count,
            "status": "CORROBORATED" if relation.swarm_consensus_count >= 2 else "SINGLE_SOURCE",
        }
        await self.kuzu.enqueue_write(cypher, params)

        # Link claim to entities
        await self.kuzu.enqueue_write(
            "MATCH (c:Claim {claim_id: $claim_id}) MATCH (e:Entity {id: $source_id}) "
            "MERGE (c)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e)",
            {"claim_id": claim_id, "source_id": relation.source_entity},
        )
        await self.kuzu.enqueue_write(
            "MATCH (c:Claim {claim_id: $claim_id}) MATCH (e:Entity {id: $target_id}) "
            "MERGE (c)-[:ASSERTS_ABOUT {role: 'OBJECT'}]->(e)",
            {"claim_id": claim_id, "target_id": relation.target_entity},
        )
