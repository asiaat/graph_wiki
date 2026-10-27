"""API routes: graph traversal, shortest path and community detection.

All queries are written against the **Kùzu** Cypher dialect, which differs
from Neo4j in several ways that matter here:

* there is no ``shortestPath()`` function and no ``MATCH SHORTEST`` clause in
  0.11.x, so the shortest path is computed with a bounded breadth-first search
  over the neighbourhood;
* there is no ``algo.louvain.stream`` procedure; the graph-algorithm functions
  in this version require a projected graph, so communities are computed from
  the connected components of the relation graph;
* ``LIMIT`` may only terminate a whole query, never a subquery.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])


class SubgraphRequest(BaseModel):
    entity_id: str
    hops: int = 2
    limit: int = 100


class PathRequest(BaseModel):
    source_id: str
    target_id: str
    max_hops: int = 5


class ClusterRequest(BaseModel):
    category: str | None = None
    min_size: int = 3
    max_hops: int = 3


async def get_kuzu():
    from kuzuwiki.main import app

    return app.state.kuzu


@router.post("/subgraph")
async def query_subgraph(req: SubgraphRequest) -> dict[str, Any]:
    """Return the k-hop neighbourhood of an entity for the graph canvas."""
    kuzu = await get_kuzu()
    hops = max(1, min(int(req.hops), 4))

    node_rows = await kuzu.read(
        f"""
        MATCH (e:Entity {{id: $entity_id}})
        MATCH (n:Entity)-[:RELATES_TO*1..{hops}]-(e)
        RETURN n.id AS id, n.canonical_name AS canonical_name,
               n.category AS category, n.confidence_score AS confidence
        """,
        {"entity_id": req.entity_id},
    )

    root_rows = await kuzu.read(
        "MATCH (e:Entity {id: $entity_id}) "
        "RETURN e.id AS id, e.canonical_name AS canonical_name, "
        "e.category AS category, e.confidence_score AS confidence",
        {"entity_id": req.entity_id},
    )
    if not root_rows:
        raise HTTPException(404, "Entity not found")

    entities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in [root_rows[0], *node_rows]:
        entity_id = row.get("id")
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        entities.append(
            {
                "id": entity_id,
                "canonical_name": row.get("canonical_name"),
                "category": row.get("category"),
                "confidence": row.get("confidence"),
            }
        )

    if len(entities) > req.limit:
        entities = entities[: req.limit]

    edge_rows = await kuzu.read(
        """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        RETURN a.id AS source, b.id AS target, r.relation_type AS relation_type,
               r.weight AS weight, r.is_disputed AS is_disputed
        """
    )
    ids = {e["id"] for e in entities}
    edges = [
        {
            "source": row["source"],
            "target": row["target"],
            "relation_type": row.get("relation_type"),
            "weight": row.get("weight"),
            "is_disputed": row.get("is_disputed"),
        }
        for row in edge_rows
        if row.get("source") in ids and row.get("target") in ids
    ]

    return {"entities": entities, "edges": edges}


@router.post("/shortest-path")
async def shortest_path(req: PathRequest) -> dict[str, Any]:
    """Shortest path between two entities, computed by bounded BFS."""
    kuzu = await get_kuzu()
    max_hops = max(1, min(int(req.max_hops), 8))

    edge_rows = await kuzu.read(
        """
        MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
        RETURN a.id AS source, b.id AS target, r.relation_type AS relation_type
        """
    )
    adjacency: dict[str, list[tuple[str, str | None]]] = {}
    for row in edge_rows:
        source, target = row.get("source"), row.get("target")
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append((target, row.get("relation_type")))
        adjacency.setdefault(target, []).append((source, row.get("relation_type")))

    path = _bfs_path(adjacency, req.source_id, req.target_id, max_hops)
    if path is None:
        return {"paths": [], "found": False}

    nodes = [req.source_id]
    relations: list[dict[str, Any]] = []
    for step in path:
        nodes.append(step["node"])
        relations.append(
            {
                "source": step["previous"],
                "target": step["node"],
                "relation_type": step.get("relation_type"),
            }
        )

    name_rows = await kuzu.read(
        "MATCH (e:Entity) WHERE e.id IN $ids "
        "RETURN e.id AS id, e.canonical_name AS canonical_name, e.category AS category",
        {"ids": nodes},
    )
    names = {row["id"]: row for row in name_rows}

    return {
        "found": True,
        "paths": [
            {
                "nodes": [
                    {
                        "id": node_id,
                        "canonical_name": names.get(node_id, {}).get("canonical_name"),
                        "category": names.get(node_id, {}).get("category"),
                    }
                    for node_id in nodes
                ],
                "relations": relations,
                "length": len(relations),
            }
        ],
    }


def _bfs_path(
    adjacency: dict[str, list[tuple[str, str | None]]],
    source: str,
    target: str,
    max_hops: int,
) -> list[dict[str, Any]] | None:
    """Breadth-first search for the shortest undirected path."""
    if source == target:
        return []
    queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(source, [])])
    visited = {source}

    while queue:
        current, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        for neighbour, relation_type in adjacency.get(current, []):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            step = {
                "previous": current,
                "node": neighbour,
                "relation_type": relation_type,
            }
            extended = [*path, step]
            if neighbour == target:
                return extended
            queue.append((neighbour, extended))
    return None


@router.post("/clusters")
async def louvain_clusters(req: ClusterRequest) -> dict[str, Any]:
    """Community detection over the entity relation graph."""
    kuzu = await get_kuzu()
    max_hops = max(1, min(int(req.max_hops), 4))

    if req.category:
        rows = await kuzu.read(
            f"""
            MATCH (seed:Entity {{category: $category}})
            MATCH (member:Entity)-[:RELATES_TO*1..{max_hops}]-(seed)
            RETURN seed.id AS seed, collect(DISTINCT member.id) AS members
            """,
            {"category": req.category},
        )
    else:
        rows = await kuzu.read(
            f"""
            MATCH (seed:Entity)
            MATCH (member:Entity)-[:RELATES_TO*1..{max_hops}]-(seed)
            RETURN seed.id AS seed, collect(DISTINCT member.id) AS members
            """
        )

    clusters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        members = [row["seed"], *[m for m in (row.get("members") or []) if m != row["seed"]]]
        if len(members) < req.min_size:
            continue
        key = tuple(sorted(members))
        if key in seen:
            continue
        seen.add(key)
        clusters.append({"members": members, "size": len(members)})

    clusters.sort(key=lambda c: c["size"], reverse=True)
    return {
        "communities": clusters,
        "algorithm": f"connected_components_{max_hops}_hops",
        "count": len(clusters),
    }


@router.get("/entities")
async def list_entities(limit: int = 100, category: str | None = None) -> dict[str, Any]:
    """List compiled entities - the left-hand ontology picker."""
    kuzu = await get_kuzu()
    if category:
        rows = await kuzu.read(
            "MATCH (e:Entity) WHERE e.category = $category "
            "RETURN e.id AS id, e.canonical_name AS canonical_name, "
            "e.category AS category, e.confidence_score AS confidence, "
            "e.lifecycle_state AS lifecycle_state "
            "ORDER BY e.canonical_name LIMIT $limit",
            {"category": category, "limit": limit},
        )
    else:
        rows = await kuzu.read(
            "MATCH (e:Entity) "
            "RETURN e.id AS id, e.canonical_name AS canonical_name, "
            "e.category AS category, e.confidence_score AS confidence, "
            "e.lifecycle_state AS lifecycle_state "
            "ORDER BY e.canonical_name LIMIT $limit",
            {"limit": limit},
        )
    return {"entities": rows, "count": len(rows)}


@router.get("/terms")
async def list_terms(limit: int = 50) -> dict[str, Any]:
    """The Lande term hierarchy persisted from the visibility graph."""
    kuzu = await get_kuzu()
    terms = await kuzu.read(
        "MATCH (t:DomainTerm) "
        "RETURN t.term AS term, t.idf_weight AS idf_weight, "
        "t.hvg_degree AS hvg_degree, t.burst_score AS burst_score "
        "ORDER BY t.hvg_degree DESC LIMIT $limit",
        {"limit": limit},
    )
    edges = await kuzu.read(
        "MATCH (a:DomainTerm)-[r:TERM_DOMINATES]->(b:DomainTerm) "
        "RETURN a.term AS source, b.term AS target, "
        "r.visibility_weight AS visibility_weight"
    )
    return {"terms": terms, "edges": edges}


@router.get("/entities/count")
async def count_entities() -> dict[str, Any]:
    """How many entities have been compiled into the graph."""
    kuzu = await get_kuzu()
    rows = await kuzu.read("MATCH (e:Entity) RETURN count(e) AS total")
    return {"total": int(rows[0]["total"]) if rows else 0}


@router.get("/entity/{entity_id}")
async def get_entity(entity_id: str) -> dict[str, Any]:
    """Fetch a single entity with its claims and relations."""
    kuzu = await get_kuzu()
    rows = await kuzu.read(
        "MATCH (e:Entity {id: $id}) "
        "RETURN e.id AS id, e.canonical_name AS canonical_name, "
        "e.category AS category, e.aliases AS aliases, e.summary AS summary, "
        "e.slug AS slug, e.confidence_score AS confidence, "
        "e.lifecycle_state AS lifecycle_state",
        {"id": entity_id},
    )
    if not rows:
        raise HTTPException(404, "Entity not found")
    return {"entity": rows[0]}
