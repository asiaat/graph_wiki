"""Orchestrator — LangGraph state machine: Ingest → Compile → Lint → Complicate."""

import logging
from typing import Any, TypedDict

from kuzuwiki.agents.gatekeeper import GatekeeperSlopAgent
from kuzuwiki.agents.swarm_extractor import SwarmExtractor
from kuzuwiki.agents.wiki_compiler import GraphWikiCompilerAgent
from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.wiki_sync import WikiSync
from kuzuwiki.jev.schemas import RawDocumentPayload
from kuzuwiki.lande.hvg_network import compute_hvg

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict, total=False):
    doc_payload: RawDocumentPayload | None
    gatekeeper_result: Any | None
    distillation_bundle: Any | None
    compile_stats: dict[str, int] | None
    lint_issues: list[str] | None
    complication_tickets: list[dict[str, Any]] | None
    error: str | None


class Orchestrator:
    def __init__(
        self,
        kuzu: KuzuClient,
        wiki_vault_path: str = "/data/wiki",
        raw_vault_path: str = "/data/raw_vault",
        swarm: SwarmExtractor | None = None,
        quarantine_path: str | None = None,
    ):
        self.kuzu = kuzu
        self.wiki_sync = WikiSync(kuzu, wiki_vault_path)
        self.gatekeeper = GatekeeperSlopAgent(
            kuzu,
            raw_vault_path,
            wiki_vault_path,
            quarantine_path=quarantine_path,
        )
        self.swarm = swarm or SwarmExtractor()
        self.compiler = GraphWikiCompilerAgent(kuzu, wiki_vault_path)

    async def ingest_and_compile(self, payload: RawDocumentPayload) -> OrchestratorState:
        state: OrchestratorState = {"error": None}

        # Step 1: Gatekeeper (slop + admiralty + archive)
        try:
            gatekeeper_result = await self.gatekeeper.ingest_document(payload)
            state["gatekeeper_result"] = gatekeeper_result
        except Exception as exc:
            state["error"] = f"Gatekeeper failed: {exc}"
            return state

        if not gatekeeper_result.accepted:
            state["error"] = f"Document quarantined: {gatekeeper_result.quarantine_reason}"
            return state

        # Step 2: Swarm extraction (if document accepted)
        try:
            hvg_result = compute_hvg(payload.content or "")
            bundle = await self.swarm.extract(
                document_text=payload.content or "",
                doc_sha256=gatekeeper_result.doc_sha256,
                hvg_hub_terms=gatekeeper_result.hub_terms,
                slop_metrics=gatekeeper_result.slop_metrics,
                hvg_result=hvg_result,
            )
            state["distillation_bundle"] = bundle
        except Exception as exc:
            state["error"] = f"Swarm extraction failed: {exc}"
            return state

        # Step 3: Compile into graph + wiki
        try:
            stats = await self.compiler.compile_bundle(bundle)
            state["compile_stats"] = stats
        except Exception as exc:
            state["error"] = f"Compilation failed: {exc}"
            return state

        return state

    async def process_osint_complication(self, entity_id: str) -> dict[str, Any]:
        """Dispatch OSINT Complicator Agent for a target entity."""
        # Fetch entity neighborhood from graph
        entity_rows = await self.kuzu.read("MATCH (e:Entity {id: $id}) RETURN e", {"id": entity_id})
        if not entity_rows:
            return {"error": f"Entity {entity_id} not found"}

        # Return task for OSINT agent
        return {
            "entity_id": entity_id,
            "task_type": "complicate_subgraph",
            "status": "dispatched",
        }
