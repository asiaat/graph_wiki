"""API routes: OSINT complication, Attack-Index time series, lint review."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/osint", tags=["osint"])


class ComplicateRequest(BaseModel):
    entity_id: str


class TicketReview(BaseModel):
    ticket_id: str
    action: str  # "approve" | "reject" | "defer"
    notes: str = ""


async def get_kuzu():
    from kuzuwiki.main import app

    return app.state.kuzu


@router.post("/complicate/{entity_id}")
async def complicate_entity(entity_id: str) -> dict[str, Any]:
    """Dispatch the OSINT Complicator Agent to deepen an entity subgraph."""
    from kuzuwiki.agents.osint_complicator import OSINTComplicatorAgent

    kuzu = await get_kuzu()
    agent = OSINTComplicatorAgent(kuzu)
    return await agent.complicate_entity(entity_id)


@router.get("/attack-index")
async def attack_index_timeseries(
    topic: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """InfoStream/Attack-Index time series, bucketed by day.

    The bucketing is done in Python because the Kùzu dialect has no
    ``datetime() - duration({...})`` and no ``date()`` truncation.
    """
    kuzu = await get_kuzu()
    window_start = datetime.now(timezone.utc) - timedelta(days=days)

    if topic:
        rows = await kuzu.read(
            """
            MATCH (s:SourceDoc)
            WHERE s.published_at IS NOT NULL AND s.published_at > $window_start
              AND s.primary_term = $topic
            RETURN s.published_at AS published_at, s.attack_index AS attack_index
            """,
            {"window_start": window_start, "topic": topic},
        )
    else:
        rows = await kuzu.read(
            """
            MATCH (s:SourceDoc)
            WHERE s.published_at IS NOT NULL AND s.published_at > $window_start
            RETURN s.published_at AS published_at, s.attack_index AS attack_index
            """,
            {"window_start": window_start},
        )

    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        published_at = row.get("published_at")
        index = row.get("attack_index")
        if published_at is None:
            continue
        day = (
            published_at.date().isoformat() if hasattr(published_at, "date") else str(published_at)
        )
        buckets[day].append(float(index) if index is not None else 0.0)

    time_series = [
        {
            "date": day,
            "avg_attack_index": sum(values) / len(values) if values else 0.0,
            "doc_count": len(values),
            "terms": [],
        }
        for day, values in sorted(buckets.items())
    ]
    return {"days": days, "topic": topic, "time_series": time_series}


@router.get("/lint/contradictions")
async def get_contradictions() -> dict[str, Any]:
    """Contradiction alerts plus the rest of the lint report."""
    from kuzuwiki.agents.linter_agent import AdversarialLinterAgent

    kuzu = await get_kuzu()
    agent = AdversarialLinterAgent(kuzu)
    report = await agent.run_lint()
    return {
        "contradictions": report["contradictions"],
        "decay_issues": report["decay_issues"],
        "wave_alerts": report["wave_alerts"],
        "structural_gaps": report["structural_gaps"],
        "timestamp": report["timestamp"],
    }


@router.get("/tickets")
async def list_tickets(status: str | None = None) -> dict[str, Any]:
    """List OSINT complication tickets for the Swarm Mentor queue."""
    kuzu = await get_kuzu()
    if status:
        rows = await kuzu.read(
            "MATCH (t:ComplicationTicket) WHERE t.status = $status "
            "RETURN t.ticket_id AS ticket_id, t.target_entity_id AS target_entity_id, "
            "t.gap_type AS gap_type, t.hypothesis_query AS hypothesis_query, "
            "t.status AS status, t.created_at AS created_at",
            {"status": status},
        )
    else:
        rows = await kuzu.read(
            "MATCH (t:ComplicationTicket) "
            "RETURN t.ticket_id AS ticket_id, t.target_entity_id AS target_entity_id, "
            "t.gap_type AS gap_type, t.hypothesis_query AS hypothesis_query, "
            "t.status AS status, t.created_at AS created_at"
        )
    tickets = []
    for row in rows:
        ticket = dict(row)
        if ticket.get("created_at") and hasattr(ticket["created_at"], "isoformat"):
            ticket["created_at"] = ticket["created_at"].isoformat()
        tickets.append(ticket)
    return {"tickets": tickets, "count": len(tickets)}


@router.post("/tickets/review")
async def review_ticket(review: TicketReview) -> dict[str, Any]:
    """Swarm Mentor decision on a complication ticket."""
    action = review.action.lower()
    if action not in ("approve", "reject", "defer"):
        raise HTTPException(400, "action must be approve, reject or defer")

    status = {"approve": "APPROVED", "reject": "REJECTED", "defer": "DEFERRED"}[action]
    kuzu = await get_kuzu()
    await kuzu.write(
        "MATCH (t:ComplicationTicket {ticket_id: $ticket_id}) SET t.status = $status",
        {"ticket_id": review.ticket_id, "status": status},
    )
    return {"ticket_id": review.ticket_id, "status": status, "notes": review.notes}
