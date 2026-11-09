"""API routes: aggregated dashboard statistics."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["stats"])


async def get_kuzu():
    from kuzuwiki.project_context import get_current_runtime

    return (await get_current_runtime()).kuzu


@router.get("/stats/dashboard")
async def get_dashboard_stats() -> dict[str, Any]:
    """Aggregate core graph statistics for the dashboard.

    Returns counts across the major node/edge types so the frontend can
    render a compact overview ribbon without N+1 round-trips.
    """
    kuzu = await get_kuzu()

    # Batch node counts in a single Cypher statement
    result = await kuzu.read(
        """
        MATCH (e:Entity)
        OPTIONAL MATCH (c:Claim)
        OPTIONAL MATCH (s:SourceDoc)
        OPTIONAL MATCH (t:ComplicationTicket {status: "OPEN"})
        OPTIONAL MATCH (g:OSINTGapTicket {status: "OPEN"})
        OPTIONAL MATCH (co:Concept)
        RETURN
            count(DISTINCT e) AS entity_count,
            count(DISTINCT c) AS claim_count,
            count(DISTINCT s) AS source_count,
            count(DISTINCT t) + count(DISTINCT g) AS open_tickets,
            count(DISTINCT co) AS concept_count
        LIMIT 1
        """,
        {},
    )

    row = result[0] if result else {}

    # Count relationships individually (cypher does not support empty node patterns)

    relates_count = 0
    try:
        rrows = await kuzu.read(
            "MATCH (e1:Entity)-[r:RELATES_TO]->(e2:Entity) RETURN count(DISTINCT r) AS cnt",
            {},
        )
        if rrows and rrows[0].get("cnt") is not None:
            relates_count = int(rrows[0]["cnt"])
    except Exception as exc:
        logger.error("Could not count RELATES_TO: %s", exc)

    evidence_count = 0
    try:
        evrows = await kuzu.read(
            "MATCH (c:Claim)-[ev:EVIDENCED_BY]->(s:SourceDoc) RETURN count(DISTINCT ev) AS cnt",
            {},
        )
        if evrows and evrows[0].get("cnt") is not None:
            evidence_count = int(evrows[0]["cnt"])
    except Exception as exc:
        logger.error("Could not count EVIDENCED_BY: %s", exc)

    reprint_count = 0
    try:
        rrows2 = await kuzu.read(
            "MATCH (s1:SourceDoc)-[re:REPRINTS_FROM]->(s2:SourceDoc) RETURN count(DISTINCT re) AS cnt",
            {},
        )
        if rrows2 and rrows2[0].get("cnt") is not None:
            reprint_count = int(rrows2[0]["cnt"])
    except Exception as exc:
        logger.error("Could not count REPRINTS_FROM: %s", exc)

    contradiction_count = 0
    try:
        crows = await kuzu.read(
            "MATCH (c1:Claim)-[ct:CONTRADICTS]->(c2:Claim) RETURN count(DISTINCT ct) AS cnt",
            {},
        )
        if crows and crows[0].get("cnt") is not None:
            contradiction_count = int(crows[0]["cnt"])
    except Exception as exc:
        logger.error("Could not count CONTRADICTS: %s", exc)

    def _val(row, key: str, default: int = 0) -> int:
        v = row.get(key)
        if v is None:
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    # Admiralty rating breakdown for sources
    admiralty_dist = await kuzu.read(
        """
        MATCH (s:SourceDoc)
        WHERE s.admiralty_reliability IS NOT NULL
        RETURN s.admiralty_reliability AS rating, count(*) AS cnt
        """,
        {},
    )
    admiralty_breakdown: dict[str, int] = {}
    for r in admiralty_dist:
        rating = str(r.get("rating", "UNKNOWN"))
        admiralty_breakdown[rating] = int(r.get("cnt", 0))

    # Entity breakdown by category
    entity_cat_rows = await kuzu.read(
        "MATCH (e:Entity) RETURN e.category AS category, count(DISTINCT e) AS cnt",
        {},
    )
    entity_by_category: dict[str, int] = {}
    for r in entity_cat_rows:
        cat = str(r.get("category", "UNKNOWN"))
        entity_by_category[cat] = int(r.get("cnt", 0))

    # Claim confidence distribution
    claim_conf_rows = await kuzu.read(
        "MATCH (c:Claim) RETURN c.confidence AS confidence",
        {},
    )
    confidence_dist = {"high": 0, "medium": 0, "low": 0}
    for r in claim_conf_rows:
        conf = r.get("confidence")
        if conf is None:
            continue
        try:
            c = float(conf)
            if c >= 0.8:
                confidence_dist["high"] += 1
            elif c >= 0.5:
                confidence_dist["medium"] += 1
            else:
                confidence_dist["low"] += 1
        except (TypeError, ValueError):
            pass

    # Recent ingestion timestamps
    ingestion_rows = await kuzu.read(
        "MATCH (s:SourceDoc) WHERE s.ingested_at IS NOT NULL RETURN s.ingested_at AS ingested_at ORDER BY s.ingested_at DESC LIMIT 5",
        {},
    )
    recent_ingestions = [
        r.get("ingested_at").isoformat() if r.get("ingested_at") else None for r in ingestion_rows
    ]

    # Quality metrics: extraction success rate and consensus
    total_claims = _val(row, "claim_count")
    claimed_with_nli = 0
    try:
        nli_rows = await kuzu.read(
            "MATCH (r:RELATES_TO) WHERE r.nli_entailment_score IS NOT NULL RETURN count(*) AS cnt",
            {},
        )
        if nli_rows and nli_rows[0].get("cnt") is not None:
            claimed_with_nli = int(nli_rows[0]["cnt"])
    except Exception as exc:
        logger.error("Could not count NLI scores: %s", exc)

    extraction_success_rate = claimed_with_nli / total_claims if total_claims > 0 else 0

    # Average NLI score
    avg_nli = 0.0
    try:
        nli_avg_rows = await kuzu.read(
            "MATCH (r:RELATES_TO) WHERE r.nli_entailment_score IS NOT NULL RETURN avg(r.nli_entailment_score) AS avg_score",
            {},
        )
        if nli_avg_rows and nli_avg_rows[0].get("avg_score") is not None:
            avg_nli = float(nli_avg_rows[0]["avg_score"])
    except Exception as exc:
        logger.error("Could not compute avg NLI: %s", exc)

    return {
        "sources": {
            "total": _val(row, "source_count"),
            "admiralty_breakdown": admiralty_breakdown,
            "quarantined": reprint_count,
        },
        "entities": {
            "total": _val(row, "entity_count"),
            "by_category": entity_by_category,
        },
        "claims": {
            "total": _val(row, "claim_count"),
            "evidenced": evidence_count,
            "confidence_distribution": confidence_dist,
        },
        "relations": {
            "relates_to": relates_count,
            "reprints": reprint_count,
        },
        "contradictions": {
            "count": contradiction_count,
        },
        "osint": {
            "open_tickets": _val(row, "open_tickets"),
            "synth_concepts": _val(row, "concept_count"),
        },
        "quality_metrics": {
            "extraction_success_rate": round(extraction_success_rate, 3),
            "average_nli_score": round(avg_nli, 3),
            "total_claims_with_nli": claimed_with_nli,
        },
        "activity": {
            "recent_ingestions": recent_ingestions,
            "last_update": recent_ingestions[0] if recent_ingestions else None,
        },
    }


@router.get("/stats/graph-health")
async def get_graph_health() -> dict[str, Any]:
    """Quick health snapshot: connectivity, coverage, anomalies."""
    kuzu = await get_kuzu()

    # Count structural gaps from the linter
    rows = await kuzu.read(
        """
        MATCH (t:ComplicationTicket)
        RETURN t.status AS status, count(*) AS cnt
        """,
        {},
    )
    ticket_status_counts: dict[str, int] = {}
    for r in rows:
        status = str(r.get("status", "UNKNOWN"))
        ticket_status_counts[status] = int(r.get("cnt", 0))

    # Check for contradictions
    rows = await kuzu.read(
        """
        MATCH ()-[c:CONTRADICTS]->()
        RETURN count(*) AS contradiction_count
        """,
        {},
    )
    contradiction_count = 0
    if rows:
        contradiction_count = int(rows[0].get("contradiction_count", 0))

    # Check for decayed claims (Ebbinghaus)
    rows = await kuzu.read(
        """
        MATCH (c:Claim)
        WHERE c.nli_entailment < 0.5
        RETURN count(*) AS decay_count
        """,
        {},
    )
    decay_count = 0
    if rows:
        decay_count = int(rows[0].get("decay_count", 0))

    return {
        "tickets_by_status": ticket_status_counts,
        "contradiction_count": contradiction_count,
        "decayed_claims": decay_count,
    }
