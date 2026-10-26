"""API Routes: Cypher subgraph queries, shortest path, Louvain clusters."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

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


async def get_kuzu():
    from app.main import app

    return app.state.kuzu


@router.post("/subgraph")
async def query_subgraph(req: SubgraphRequest) -> dict[str, Any]:
    """Return k-hop subgraph around entity for graph canvas."""
    kuzu = await get_kuzu()
    cypher = f"""
    MATCH (e:Entity {{id: $entity_id}})
    CALL {{
        MATCH path = (e)-[:RELATES_TO*1..{req.hops}]-(n)
        RETURN path
        LIMIT {req.limit}
    }}
    RETURN path
    """
    rows = await kuzu.read(cypher, {"entity_id": req.entity_id})
    return {"paths": rows}


@router.post("/shortest-path")
async def shortest_path(req: PathRequest) -> dict[str, Any]:
    """Shortest path between two entities."""
    kuzu = await get_kuzu()
    cypher = f"""
    MATCH (src:Entity {{id: $source_id}}), (tgt:Entity {{id: $target_id}})
    MATCH path = shortestPath((src)-[:RELATES_TO*1..{req.max_hops}]-(tgt))
    RETURN path
    """
    rows = await kuzu.read(cypher, {"source_id": req.source_id, "target_id": req.target_id})
    return {"paths": rows}


@router.post("/clusters")
async def louvain_clusters(req: ClusterRequest) -> dict[str, Any]:
    """Louvain community detection on Entity graph."""
    kuzu = await get_kuzu()
    where = f"WHERE e.category = '{req.category}'" if req.category else ""
    cypher = f"""
    CALL algo.louvain.stream('Entity', 'RELATES_TO', {{}})
    YIELD nodeId, communityId
    MATCH (e:Entity) WHERE id(e) = nodeId
    RETURN communityId, collect(e.id) as members
    HAVING size(members) >= {req.min_size}
    """
    rows = await kuzu.read(cypher)
    return {"communities": rows}


@router.get("/entity/{entity_id}")
async def get_entity(entity_id: str) -> dict[str, Any]:
    kuzu = await get_kuzu()
    rows = await kuzu.read("MATCH (e:Entity {id: $id}) RETURN e", {"id": entity_id})
    if not rows:
        raise HTTPException(404, "Entity not found")
    return {"entity": rows[0]}
