"""API Routes: Complication tickets, Attack-Index time series, Swarm Mentor review."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/osint", tags=["osint"])


class ComplicateRequest(BaseModel):
    entity_id: str


class TicketReview(BaseModel):
    ticket_id: str
    action: str  # "approve" | "reject" | "defer"
    notes: str = ""


async def get_kuzu():
    from app.main import app

    return app.state.kuzu


@router.post("/complicate/{entity_id}")
async def complicate_entity(entity_id: str) -> dict[str, Any]:
    """Dispatch OSINT Complicator Agent to deepen entity subgraph."""
    from app.agents.osint_complicator import OSINTComplicatorAgent

    kuzu = await get_kuzu()
    agent = OSINTComplicatorAgent(kuzu)
    result = await agent.complicate_entity(entity_id)
    return result


@router.get("/attack-index")
async def attack_index_timeseries(
    topic: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """InfoStream/Attack-Index time-series histograms, wave anomalies, reprint cascades."""
    kuzu = await get_kuzu()
    cypher = """
    MATCH (s:SourceDoc)
    WHERE s.published_at > datetime() - duration({days: $days})
    RETURN date(s.published_at) as day, avg(s.attack_index) as avg_attack,
           count(*) as doc_count, collect(s.term) as terms
    ORDER BY day
    """
    rows = await kuzu.read(cypher, {"days": days})
    return {
        "days": days,
        "time_series": [
            {"date": str(r[0]), "avg_attack_index": r[1], "doc_count": r[2], "terms": r[3]}
            for r in rows
        ],
    }


@router.get("/lint/contradictions")
async def get_contradictions() -> dict[str, Any]:
    """All active CONTRADICTS edges with side-by-side source quotes."""
    from app.agents.linter_agent import AdversarialLinterAgent

    kuzu = await get_kuzu()
    agent = AdversarialLinterAgent(kuzu)
    result = await agent.run_lint()
    return result
