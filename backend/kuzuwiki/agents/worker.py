"""Celery worker for the background compilation, lint and OSINT loop.

Registered tasks (ARCHIT.md §4):

* ``ingest_and_compile``   — Gatekeeper → HVG → JEV Swarm → Wiki Compiler
* ``run_lint``              — AdversarialLinterAgent contradiction / decay / wave / gap checks
* ``complicate_entity``     — OSINTComplicatorAgent deep-research dispatch

The worker is started with::

    celery -A kuzuwiki.agents.worker.app worker --beat --loglevel=info --concurrency=2

``--beat`` enables the periodic schedule below, which calls ``run_lint``
every 5 minutes and polls for orphaned ComplicationTicket nodes every minute.
"""

from __future__ import annotations

import asyncio
import logging
import os

from celery import Celery

from kuzuwiki.config import settings

logger = logging.getLogger(__name__)

_BROKER = os.environ.get("REDIS_URL", settings.redis_url)

app = Celery(
    "kuzuwiki-worker",
    broker=_BROKER,
    backend=_BROKER,
    include=["kuzuwiki.agents.worker"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json", "msgpack"],
    timezone="UTC",
    beat_schedule={
        "lint-every-5-minutes": {
            "task": "kuzuwiki.agents.worker.run_lint",
            "schedule": 300.0,
        },
        "poll-open-tickets": {
            "task": "kuzuwiki.agents.worker.poll_open_tickets",
            "schedule": 60.0,
        },
    },
)


def _run_async(coro):
    """Wrap a coroutine so Celery's sync task can run it."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@app.task(bind=True, name="kuzuwiki.agents.worker.ingest_and_compile")
def ingest_and_compile_task(self, payload: dict) -> dict:
    """Run the full ingest → compile pipeline for a single document."""
    from kuzuwiki.agents.orchestrator import Orchestrator
    from kuzuwiki.db.kuzu_client import KuzuClient
    from kuzuwiki.db.schema_init import ensure_schema
    from kuzuwiki.jev.schemas import RawDocumentPayload

    doc_payload = RawDocumentPayload(**payload)

    async def _run() -> dict:
        kuzu = await KuzuClient.init(settings.kuzu_db_path)
        try:
            await ensure_schema(kuzu)
            orchestrator = Orchestrator(
                kuzu,
                wiki_vault_path=settings.wiki_vault_path,
                raw_vault_path=settings.raw_vault_path,
                quarantine_path=settings.quarantine_path,
            )
            state = await orchestrator.ingest_and_compile(doc_payload)
            return state
        finally:
            await kuzu.close()
            KuzuClient._shared_instance = None

    return _run_async(_run())


@app.task(bind=True, name="kuzuwiki.agents.worker.run_lint")
def run_lint_task(self) -> dict:
    """Run all scheduled lint checks."""
    from kuzuwiki.agents.linter_agent import AdversarialLinterAgent
    from kuzuwiki.db.kuzu_client import KuzuClient
    from kuzuwiki.db.schema_init import ensure_schema

    async def _run() -> dict:
        kuzu = await KuzuClient.init(settings.kuzu_db_path)
        try:
            await ensure_schema(kuzu)
            agent = AdversarialLinterAgent(kuzu)
            return await agent.run_lint()
        finally:
            await kuzu.close()
            KuzuClient._shared_instance = None

    return _run_async(_run())


@app.task(bind=True, name="kuzuwiki.agents.worker.complicate_entity")
def complicate_entity_task(self, entity_id: str) -> dict:
    """Dispatch OSINT Complicator Agent for a target entity."""
    from kuzuwiki.agents.osint_complicator import OSINTComplicatorAgent
    from kuzuwiki.db.kuzu_client import KuzuClient
    from kuzuwiki.db.schema_init import ensure_schema

    async def _run() -> dict:
        kuzu = await KuzuClient.init(settings.kuzu_db_path)
        try:
            await ensure_schema(kuzu)
            agent = OSINTComplicatorAgent(kuzu)
            return await agent.complicate_entity(entity_id)
        finally:
            await kuzu.close()
            KuzuClient._shared_instance = None

    return _run_async(_run())


@app.task(bind=True, name="kuzuwiki.agents.worker.poll_open_tickets")
def poll_open_tickets_task(self) -> dict:
    """Check for unreviewed ComplicationTicket nodes."""
    from kuzuwiki.db.kuzu_client import KuzuClient
    from kuzuwiki.db.schema_init import ensure_schema

    async def _run() -> dict:
        kuzu = await KuzuClient.init(settings.kuzu_db_path)
        try:
            await ensure_schema(kuzu)
            rows = await kuzu.read(
                "MATCH (t:ComplicationTicket) WHERE t.status = 'OPEN' "
                "RETURN t.ticket_id AS ticket_id, t.target_entity_id AS target_entity_id, "
                "t.gap_type AS gap_type, t.hypothesis_query AS hypothesis_query, "
                "t.created_at AS created_at"
            )
            tickets = []
            for row in rows:
                ticket = dict(row)
                if ticket.get("created_at") and hasattr(ticket["created_at"], "isoformat"):
                    ticket["created_at"] = ticket["created_at"].isoformat()
                tickets.append(ticket)
            return {"open_tickets": tickets, "count": len(tickets)}
        finally:
            await kuzu.close()
            KuzuClient._shared_instance = None

    return _run_async(_run())


@app.task(bind=True, name="kuzuwiki.agents.worker.sync_wiki")
def sync_wiki_task(self) -> dict:
    """Re-sync all wiki markdown from the KùzuDB graph."""
    from kuzuwiki.db.kuzu_client import KuzuClient
    from kuzuwiki.db.schema_init import ensure_schema
    from kuzuwiki.db.wiki_sync import WikiSync

    async def _run() -> dict:
        kuzu = await KuzuClient.init(settings.kuzu_db_path)
        try:
            await ensure_schema(kuzu)
            wiki_sync = WikiSync(kuzu, settings.wiki_vault_path)
            await wiki_sync.sync_all_entities()
            return {"synced": True}
        finally:
            await kuzu.close()
            KuzuClient._shared_instance = None

    return _run_async(_run())
