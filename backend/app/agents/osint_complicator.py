"""Agent 6: OSINTComplicatorAgent — Autonomous Deep Research & Knowledge Enhancer."""

import asyncio
import logging
import os
from typing import Any

import httpx

from app.config import settings
from app.db.kuzu_client import KuzuClient

logger = logging.getLogger(__name__)


class OSINTComplicatorAgent:
    def __init__(self, kuzu: KuzuClient):
        self.kuzu = kuzu

    async def complicate_entity(self, entity_id: str) -> dict[str, Any]:
        """Hunt for missing facts, verify claims, expand entity subgraph."""
        # Fetch entity neighborhood
        entity_rows = await self.kuzu.read("MATCH (e:Entity {id: $id}) RETURN e", {"id": entity_id})
        if not entity_rows:
            return {"error": f"Entity {entity_id} not found"}

        # Generate search queries
        queries = await self._formulate_dorks(entity_id)
        logger.info("Formulated %d OSINT queries for %s", len(queries), entity_id)

        # Search via SearXNG
        results = await self._search_searxng(queries)
        logger.info("Retrieved %d search results", len(results))

        # Create ComplicationTicket nodes
        tickets = []
        for result in results:
            ticket_id = f"ticket-{entity_id}-{result.get('title', 'unknown')[:32]}"
            cypher = """
            MERGE (t:ComplicationTicket {ticket_id: $ticket_id})
            ON CREATE SET
                t.target_entity_id = $entity_id,
                t.gap_type = 'UNVERIFIED_CLAIM',
                t.hypothesis_query = $query,
                t.status = 'OPEN',
                t.created_at = $created_at
            """
            await self.kuzu.enqueue_write(
                cypher,
                {
                    "ticket_id": ticket_id,
                    "entity_id": entity_id,
                    "query": result.get("query", ""),
                    "created_at": "2024-01-01T00:00:00Z",
                },
            )
            tickets.append(ticket_id)

        return {
            "entity_id": entity_id,
            "queries_formulated": len(queries),
            "results_retrieved": len(results),
            "tickets_created": tickets,
        }

    async def _formulate_dorks(self, entity_id: str) -> list[str]:
        """Generate targeted OSINT search queries based on entity context."""
        # Fetch entity details
        rows = await self.kuzu.read(
            "MATCH (e:Entity {id: $id}) RETURN e.canonical_name, e.category, e.external_ids",
            {"id": entity_id},
        )
        if not rows:
            return []

        name = rows[0][0]
        category = rows[0][1]
        external_ids = rows[0][2] or {}

        queries = [
            f'"{name}" site:opencorporates.com',
            f'"{name}" sanctions list',
            f'"{name}" drone component supply chain',
            f'"{name}" beneficial ownership',
        ]

        # Add ID-specific dorks
        for key, val in external_ids.items():
            queries.append(f'"{val}" {key} registry')

        return queries

    async def _search_searxng(self, queries: list[str]) -> list[dict[str, Any]]:
        """Execute sandboxed web searches via SearXNG."""
        results = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in queries[:5]:  # Limit to 5 queries per call
                try:
                    resp = await client.get(
                        f"{settings.searxng_url}/search",
                        params={"q": query, "format": "json"},
                        headers={"Accept": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("results", []):
                            results.append(
                                {
                                    "title": item.get("title", ""),
                                    "url": item.get("url", ""),
                                    "snippet": item.get("content", ""),
                                    "query": query,
                                }
                            )
                except Exception as exc:
                    logger.error("SearXNG query failed: %s", exc)

        return results
