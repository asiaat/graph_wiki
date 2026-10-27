"""Shared pytest fixtures for the KuzuWiki-OSINT backend."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def backend_root() -> Path:
    return BACKEND_ROOT


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Isolated raw/wiki vault pair."""
    raw = tmp_path / "raw_vault"
    wiki = tmp_path / "wiki"
    raw.mkdir()
    wiki.mkdir()
    return raw, wiki


@pytest.fixture
def env_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee the pipeline never silently depends on a live OpenRouter key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def kuzu_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "kuzu_test_db")


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Keep settings pointed at scratch dirs so tests never touch real voles."""
    from kuzuwiki.config import settings

    monkeypatch.setattr(settings, "raw_vault_path", str(tmp_path / "raw_vault"))
    monkeypatch.setattr(settings, "wiki_vault_path", str(tmp_path / "wiki"))
    monkeypatch.setattr(settings, "quarantine_path", str(tmp_path / "quarantine"))
    # KùzuDB needs a *file* path, so the scratch path must be a file too.
    monkeypatch.setattr(settings, "kuzu_db_path", str(tmp_path / "kuzudb" / "graph.kuzu"))
    (tmp_path / "raw_vault").mkdir(exist_ok=True)
    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "quarantine").mkdir(exist_ok=True)
    (tmp_path / "kuzudb").mkdir(exist_ok=True)
    yield


@pytest.fixture
def offline_env(monkeypatch: pytest.MonkeyPatch):
    """Force every network call in the codebase to fail loudly.

    Tests must exercise the offline/degraded paths explicitly rather than
    accidentally reaching OpenRouter or SearXNG.
    """
    import httpx

    def _boom(*args, **kwargs):
        raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    monkeypatch.setattr(httpx, "Client", _boom)
    monkeypatch.setattr(httpx, "get", _boom)
    monkeypatch.setattr(httpx, "post", _boom)
    yield


@pytest.fixture(autouse=True)
def _no_stray_writes():
    """Fail loudly if a test writes outside tmp_path."""
    cwd = os.getcwd()
    yield
    assert os.getcwd() == cwd


# ---------------------------------------------------------------------------
# Shared pipeline fixtures
# ---------------------------------------------------------------------------

#: A document with two verifiable, clearly-worded relations.
SAMPLE_DOC = (
    "Acme Corporation manufactures the X-200 drone airframe for Beta Systems. "
    "The agreement signed on 12 March 2024 obliges Beta Systems to supply rotor "
    "components to Acme Corporation until December 2025. Registry filings list "
    "Acme Corporation under company number 08842119."
)


class FakeOpenRouter:
    """Stands in for OpenRouterClient; returns the same payload to every expert."""

    fallback_models: list[str] = []

    def __init__(self, payload: dict | None = None):
        self.calls: list[dict] = []
        self.payload = payload

    async def chat_completion(
        self,
        system_prompt: str,
        text: str,
        model_override: str | None = None,
        temperature: float = 0.0,
    ) -> dict:
        self.calls.append(
            {"system_prompt": system_prompt, "temperature": temperature, "model": model_override}
        )
        payload = self.payload if self.payload is not None else DEFAULT_EXPERT_PAYLOAD
        return {"content": json.dumps(payload)}


DEFAULT_EXPERT_PAYLOAD = {
    "entities": [
        {
            "canonical_name": "Acme Corporation",
            "category": "Organization",
            "aliases": ["Acme"],
            "deterministic_ids": {"company_number": "08842119"},
            "summary_fact": "Acme Corporation manufactures the X-200 drone airframe.",
            "evidence": {
                "source_doc_sha256": "sha",
                "exact_quote": "Acme Corporation manufactures the X-200 drone airframe for Beta Systems.",
                "start_char": 0,
                "end_char": 0,
            },
            "confidence": 0.9,
        },
        {
            "canonical_name": "Beta Systems",
            "category": "Organization",
            "aliases": [],
            "deterministic_ids": {},
            "summary_fact": "Beta Systems supplies rotor components to Acme Corporation.",
            "evidence": {
                "source_doc_sha256": "sha",
                "exact_quote": "obliges Beta Systems to supply rotor components to Acme Corporation",
                "start_char": 0,
                "end_char": 0,
            },
            "confidence": 0.85,
        },
    ],
    "relations": [
        {
            "source_entity": "Acme Corporation",
            "target_entity": "Beta Systems",
            "relation_type": "MANUFACTURES",
            "nli_entailment_score": 0.9,
            "swarm_consensus_count": 2,
            "evidence": {
                "source_doc_sha256": "sha",
                "exact_quote": "Acme Corporation manufactures the X-200 drone airframe for Beta Systems.",
                "start_char": 0,
                "end_char": 0,
            },
        },
        {
            "source_entity": "Beta Systems",
            "target_entity": "Acme Corporation",
            "relation_type": "SUPPLIES_COMPONENT",
            "nli_entailment_score": 0.9,
            "swarm_consensus_count": 2,
            "evidence": {
                "source_doc_sha256": "sha",
                "exact_quote": "obliges Beta Systems to supply rotor components to Acme Corporation",
                "start_char": 0,
                "end_char": 0,
            },
        },
    ],
}


@pytest.fixture
async def graph(tmp_path, kuzu_db_path: str):
    """A KùzuDB client with the full schema applied."""
    from kuzuwiki.db.kuzu_client import KuzuClient
    from kuzuwiki.db.schema_init import ensure_schema

    client = await KuzuClient.init(kuzu_db_path)
    await ensure_schema(client)
    try:
        yield client
    finally:
        await client.close()
        KuzuClient._shared_instance = None


def build_swarm(router):
    """Build a SwarmExtractor backed by a fake router."""
    from kuzuwiki.agents.swarm_extractor import SwarmExtractor

    return SwarmExtractor(openrouter_client=router)


@pytest.fixture
def orchestrator(graph, tmp_path):
    """An orchestrator wired to a fake OpenRouter."""
    from kuzuwiki.agents.orchestrator import Orchestrator

    raw = tmp_path / "raw"
    wiki = tmp_path / "wiki"
    raw.mkdir(exist_ok=True)
    wiki.mkdir(exist_ok=True)
    router = FakeOpenRouter()
    orch = Orchestrator(
        graph,
        wiki_vault_path=str(wiki),
        raw_vault_path=str(raw),
        swarm=build_swarm(router),
    )
    orch.fake_router = router
    return orch
