"""API routes: evidence-filtered graph queries and WebSocket live updates.

The query endpoint returns ranked claims with provenance and explicitly declines
when verified evidence is missing. The WebSocket remains a heartbeat placeholder.

* ``POST /api/v1/query/compiled`` — verified claim lookup over KùzuDB
* ``WS /ws``               — heartbeat placeholder
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    entity_id: str | None = None
    save_to_wiki: bool = False
    save_to_graph: bool = False


async def get_kuzu():
    from kuzuwiki.project_context import get_current_runtime

    return (await get_current_runtime()).kuzu


_QUERY_STOPWORDS = {
    "about", "after", "against", "and", "are", "between", "did", "does", "for",
    "from", "has", "have", "how", "into", "its", "was", "were", "what", "when",
    "where", "which", "who", "why", "with", "the", "this", "that", "their", "they",
    "will", "would", "can", "could", "company", "entity",
}


def _query_terms(question: str) -> set[str]:
    return {
        _normalize_query_token(token)
        for token in re.findall(r"[a-z0-9]{3,}", question.casefold())
        if token not in _QUERY_STOPWORDS
    }


def _normalize_query_token(token: str) -> str:
    """Normalize common English plurals so ``manufacture`` finds ``manufactures``."""
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith(("ches", "shes", "sses", "xes", "zes")):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


async def _open_gap_ticket(kuzu: Any, req: QueryRequest) -> str:
    """Persist a reviewable gap when verified graph evidence is insufficient."""
    ticket_id = "gap-" + hashlib.sha256(
        f"{req.entity_id or ''}|{req.question.strip().casefold()}".encode()
    ).hexdigest()[:16]
    await kuzu.write(
        """
        MERGE (t:OSINTGapTicket {ticket_id: $ticket_id})
        ON CREATE SET
            t.target_entity_id = $entity_id,
            t.gap_description = $question,
            t.required_evidence = $required_evidence,
            t.confidence_threshold = 0.70,
            t.status = 'OPEN',
            t.created_at = $created_at
        """,
        {
            "ticket_id": ticket_id,
            "entity_id": req.entity_id or "",
            "question": req.question.strip(),
            "required_evidence": (
                "A claim with confidence >= 0.70, NLI entailment >= 0.85, a verbatim "
                "quote linked to a source document, and no unresolved contradiction."
            ),
            "created_at": datetime.now(timezone.utc),
        },
    )
    return ticket_id


@router.post("/query/compiled")
async def compiled_graph_query(req: QueryRequest) -> dict[str, Any]:
    """Return ranked, provenance-backed claims or an explicit evidence gap.

    This endpoint deliberately does not invent a narrative answer: each finding
    is a graph claim with a qualifying confidence score and a source quote.
    """
    kuzu = await get_kuzu()
    terms = _query_terms(req.question)
    if not terms and not req.entity_id:
        ticket_id = await _open_gap_ticket(kuzu, req)
        return {
            "status": "INSUFFICIENT_VERIFIED_EVIDENCE",
            "answer": "INSUFFICIENT_VERIFIED_EVIDENCE",
            "findings": [],
            "verified_claim_count": 0,
            "gap_ticket_id": ticket_id,
            "filed_synthesis_id": None,
        }
    raw_claims = await kuzu.read(
        """
        MATCH (c:Claim)-[:ASSERTS_ABOUT]->(e:Entity)
        WHERE ($entity_id = '' OR e.id = $entity_id)
        OPTIONAL MATCH (c)-[ev:EVIDENCED_BY]->(s:SourceDoc)
        OPTIONAL MATCH (c)-[contra_out:CONTRADICTS]->()
        OPTIONAL MATCH ()-[contra_in:CONTRADICTS]->(c)
        RETURN c.claim_id AS claim_id, c.statement AS statement,
               c.confidence AS confidence, c.nli_entailment AS entailment,
               c.swarm_votes AS votes,
               count(DISTINCT contra_out) + count(DISTINCT contra_in) AS contradiction_count,
               e.id AS entity_id,
               e.canonical_name AS entity_name, e.category AS entity_category,
               ev.exact_quote AS quote, s.sha256 AS source_sha256,
               s.uri AS source_uri, s.title AS source_title,
               s.admiralty_reliability AS source_reliability,
               s.credibility_rank AS source_credibility
        LIMIT 5000
        """,
        {"entity_id": req.entity_id or ""},
    )

    # A claim can be linked to both subject and object entities. Merge those
    # rows by claim ID while retaining all named entities in its answer context.
    grouped: dict[str, dict[str, Any]] = {}
    for row in raw_claims:
        claim_id = row.get("claim_id")
        if not claim_id:
            continue
        claim = grouped.setdefault(
            claim_id,
            {
                "claim_id": claim_id,
                "statement": row.get("statement") or "",
                "confidence": float(row.get("confidence") or 0.0),
                "entailment": float(row.get("entailment") or 0.0),
                "votes": int(row.get("votes") or 0),
                "contradiction_count": int(row.get("contradiction_count") or 0),
                "entities": [],
                "quote": row.get("quote"),
                "source_sha256": row.get("source_sha256"),
                "source_uri": row.get("source_uri"),
                "source_title": row.get("source_title"),
                "source_reliability": row.get("source_reliability"),
                "source_credibility": row.get("source_credibility"),
            },
        )
        entity = {
            "id": row.get("entity_id"),
            "canonical_name": row.get("entity_name"),
            "category": row.get("entity_category"),
        }
        if entity["id"] and all(existing["id"] != entity["id"] for existing in claim["entities"]):
            claim["entities"].append(entity)

    findings: list[dict[str, Any]] = []
    for claim in grouped.values():
        statement = claim["statement"].casefold()
        entity_text = " ".join(e["canonical_name"] or "" for e in claim["entities"]).casefold()
        quote = claim.get("quote") or ""
        haystack_terms = _query_terms(f"{statement} {entity_text} {quote}")
        matched_terms = sorted(terms & haystack_terms)
        relevance = len(matched_terms) / len(terms) if terms else 1.0
        has_source_evidence = bool(claim.get("source_sha256") and quote.strip())
        is_verified = (
            claim["confidence"] >= 0.70
            and claim["entailment"] >= 0.85
            and claim["contradiction_count"] == 0
            and has_source_evidence
        )
        if not is_verified or (terms and not matched_terms):
            continue
        claim["relevance"] = round(relevance, 3)
        claim["matched_terms"] = matched_terms
        findings.append(claim)

    findings.sort(key=lambda item: (item["relevance"], item["confidence"], item["entailment"]), reverse=True)
    findings = findings[:20]

    ticket_id: str | None = None
    if findings:
        status = "ANSWERED"
        synthesis = "\n".join(
            f"- {item['statement']} [source {item['source_sha256']}]"
            for item in findings
        )
    else:
        status = "INSUFFICIENT_VERIFIED_EVIDENCE"
        synthesis = status
        ticket_id = await _open_gap_ticket(kuzu, req)

    # Never persist an unsupported answer as a graph synthesis.
    filed_synthesis_id: str | None = None
    if findings and (req.save_to_wiki or req.save_to_graph):
        try:
            synthesis_id = "synthesis-" + hashlib.sha256(synthesis.encode()).hexdigest()[:12]
            filed_synthesis_id = synthesis_id

            await kuzu.write(
                """
                MERGE (s:Concept {id: $id})
                ON CREATE SET
                    s.slug = $slug,
                    s.name = $name,
                    s.definition = $definition,
                    s.wiki_markdown = $wiki,
                    s.confidence_score = $confidence,
                    s.updated_at = $updated_at
                """,
                {
                    "id": synthesis_id,
                    "slug": synthesis_id,
                    "name": f"Evidence for {req.entity_id or req.question[:80]}",
                    "definition": synthesis[:8000],
                    "wiki": synthesis[:50000],
                    "confidence": min(item["confidence"] for item in findings),
                    "updated_at": datetime.now(timezone.utc),
                },
            )

            # Link to source entity if provided
            if req.entity_id:
                await kuzu.write(
                    "MATCH (c:Concept {id: $synthesis}) MATCH (e:Entity {id: $entity_id}) "
                    "MERGE (e)-[:SYNTHESIS_FOR]->(c)",
                    {"synthesis": synthesis_id, "entity_id": req.entity_id},
                )
        except Exception as exc:
            logger.error("Failed to persist synthesis: %s", exc)

    return {
        "status": status,
        "answer": synthesis,
        "findings": findings,
        "verified_claim_count": len(findings),
        "gap_ticket_id": ticket_id,
        "filed_synthesis_id": filed_synthesis_id,
    }


@router.websocket("/ws")
async def websocket_graph_updates(websocket: WebSocket):
    """WebSocket endpoint for live graph mutation streams.

    Clients can optionally provide ``entity_id`` query parameter to receive
    updates specific to a single entity. Updates include:

    * new Entity nodes
    * new Claim nodes with provenance
    * newly discovered RELATES_TO edges
    * CONTRADICTS edges from the adversarial linter

    The connection is validated against the current backend list of supported
    clients (not implemented yet) to prevent spam injection.
    """
    entity_id = websocket.query_params.get("entity_id", "")

    await websocket.accept(subprotocols=["kuzu-graph-v1"])

    try:
        # Acknowledge connection
        await websocket.send_json(
            {"type": "system", "event": "connected", "data": {"entity_id": entity_id}}
        )

        # For now, this is a placeholder that sends periodic heartbeats.
        # Real implementation would hook into the KùzuDB change stream or
        # subscribe to agent task completions.
        # The agent workflow already has an internal write-queue actor
        # that serializes mutations, so we could expose that via a callback.

        while True:
            # Send heartbeat every 30 seconds to keep connection alive
            await websocket.send_json(
                {
                    "type": "system",
                    "event": "heartbeat",
                    "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
                }
            )

            # TODO: Real-time graph mutation streams
            # - Subscribe to KùzuDB change stream (if supported)
            # - Listen to agent task completions (Celery result backend)
            # - Check for new ComplicationTicket nodes
            # - Report contradiction detection events

            try:
                # Wait 30 seconds before next heartbeat
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected (entity_id=%s)", entity_id)
    except Exception as exc:
        logger.error("WebSocket error for entity_id %s: %s", entity_id, exc)
        try:
            await websocket.close(code=1011, reason=str(exc))
        except Exception:
            pass
