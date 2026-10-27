"""Agent 6: OSINTComplicatorAgent — autonomous deep research.

The agent hunts for the facts the graph is missing. Its search queries come
from the declarative domain packs (``osint_templates``), so a drone-supply-chain
investigation searches customs registries while a corporate-OSINT
investigation searches company registries.

Every hit is turned into a **ComplicationTicket** - a durable, reviewable
record of a gap - rather than being written straight into the compiled graph.
Documents that warrant compilation must re-enter through the Gatekeeper, so
the anti-slop and verbatim gates cannot be bypassed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from kuzuwiki.config import settings
from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.lande.domain_schema import load_all_schemas, load_schema

logger = logging.getLogger(__name__)

#: How many queries to dispatch per complication run.
MAX_QUERIES = 5


class OSINTComplicatorAgent:
    def __init__(self, kuzu: KuzuClient, searxng_url: str | None = None):
        self.kuzu = kuzu
        self.searxng_url = searxng_url or settings.searxng_url

    async def complicate_entity(self, entity_id: str) -> dict[str, Any]:
        """Hunt for missing facts, verify claims, expand the entity subgraph."""
        entity_rows = await self.kuzu.read(
            "MATCH (e:Entity {id: $id}) RETURN e.canonical_name AS canonical_name, "
            "e.category AS category, e.external_ids AS external_ids, "
            "e.aliases AS aliases",
            {"id": entity_id},
        )
        if not entity_rows:
            return {"error": f"Entity {entity_id} not found"}

        queries = await self._formulate_dorks(entity_id, entity_rows[0])
        logger.info("Formulated %d OSINT queries for %s", len(queries), entity_id)

        results = await self._search_searxng(queries)
        logger.info("Retrieved %d search results", len(results))

        tickets = []
        for result in results:
            ticket_id = await self._open_ticket(entity_id, result)
            if ticket_id:
                tickets.append(ticket_id)

        return {
            "entity_id": entity_id,
            "queries_formulated": len(queries),
            "results_retrieved": len(results),
            "tickets_created": tickets,
        }

    async def _formulate_dorks(self, entity_id: str, row: dict[str, Any]) -> list[str]:
        """Build targeted search queries from the domain pack and the entity."""
        name = str(row.get("canonical_name") or entity_id)
        external_ids = self._coerce_ids(row.get("external_ids"))
        aliases = row.get("aliases") or []

        schema = self._schema_for(row.get("category"))
        queries: list[str] = []
        if schema is not None:
            queries.extend(schema.dorks_for(name))

        # Generic fallbacks so every entity can be researched.
        queries.append(f'"{name}" site:opencorporates.com')
        queries.append(f'"{name}" sanctions list')
        queries.append(f'"{name}" beneficial ownership')

        for key, value in external_ids.items():
            queries.append(f'"{value}" {key} registry')
        for alias in aliases:
            queries.append(f'"{alias}" "{name}"')

        # Preserve order while removing duplicates.
        seen: set[str] = set()
        unique: list[str] = []
        for query in queries:
            if query and query not in seen:
                seen.add(query)
                unique.append(query)
        return unique[:MAX_QUERIES]

    @staticmethod
    def _schema_for(category: str | None) -> Any:
        """Pick the domain pack whose entity vocabulary contains this category."""
        if not category:
            return None
        schemas = load_all_schemas()
        for schema in schemas.values():
            if category in schema.entity_types:
                return schema
        return load_schema(category)

    @staticmethod
    def _coerce_ids(value: Any) -> dict[str, str]:
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

    async def _open_ticket(self, entity_id: str, result: dict[str, Any]) -> str | None:
        """Record a gap as a reviewable ComplicationTicket."""
        ticket_id = (
            "ticket-"
            + hashlib.sha256(
                f"{entity_id}|{result.get('url', '')}|{result.get('query', '')}".encode()
            ).hexdigest()[:12]
        )
        try:
            await self.kuzu.write(
                """
                MERGE (t:ComplicationTicket {ticket_id: $ticket_id})
                ON CREATE SET
                    t.target_entity_id = $entity_id,
                    t.gap_type = 'UNVERIFIED_CLAIM',
                    t.hypothesis_query = $query,
                    t.generated_dorks = $dorks,
                    t.status = 'OPEN',
                    t.created_at = $created_at
                """,
                {
                    "ticket_id": ticket_id,
                    "entity_id": entity_id,
                    "query": result.get("query", ""),
                    "dorks": [result.get("query", "")],
                    "created_at": datetime.now(timezone.utc),
                },
            )
            return ticket_id
        except Exception as exc:
            logger.error("Could not open ComplicationTicket: %s", exc)
            return None

    async def _search_searxng(self, queries: list[str]) -> list[dict[str, Any]]:
        """Execute sandboxed web searches via SearXNG."""
        results: list[dict[str, Any]] = []
        if not self.searxng_url:
            logger.warning("No SearXNG configured; skipping web retrieval")
            return results

        async with httpx.AsyncClient(timeout=30.0) as client:
            for query in queries[:MAX_QUERIES]:
                try:
                    resp = await client.get(
                        f"{self.searxng_url.rstrip('/')}/search",
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
