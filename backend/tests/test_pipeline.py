"""WP-5 gate: the full vertical slice, document -> graph -> wiki dossier.

Runs the orchestrator against a mocked OpenRouter so the whole pipeline is
exercised offline and deterministically. The assertions encode the product's
core promise: **every compiled claim carries verbatim provenance**.
"""

from __future__ import annotations

import json

from kuzuwiki.jev.schemas import RawDocumentPayload

from .conftest import DEFAULT_EXPERT_PAYLOAD, FakeOpenRouter
from .conftest import SAMPLE_DOC as DOC


async def test_ingest_produces_entities_relations_and_provenance(orchestrator):
    state = await orchestrator.ingest_and_compile(
        RawDocumentPayload(
            content=DOC,
            title="Drone supply chain report",
            domain="reuters.com",
            published_at="2024-03-12",
        )
    )
    assert state["error"] is None, state["error"]

    stats = state["compile_stats"]
    assert stats["entities"] >= 2
    assert stats["relations"] >= 1
    assert stats["claims"] >= 1
    assert stats["provenance_edges"] >= 1

    # The graph holds the entities...
    entities = await orchestrator.kuzu.read(
        "MATCH (e:Entity) RETURN e.canonical_name AS name, e.slug AS slug, "
        "e.summary AS summary, e.confidence_score AS confidence, "
        "e.lifecycle_state AS lifecycle"
    )
    names = {row["name"] for row in entities}
    assert "Acme Corporation" in names
    assert "Beta Systems" in names

    # ...and every claim is linked to its entities by id.
    links = await orchestrator.kuzu.read(
        "MATCH (c:Claim)-[a:ASSERTS_ABOUT]->(e:Entity) "
        "RETURN c.claim_id AS claim_id, e.id AS entity_id, a.role AS role"
    )
    assert links, "claims must be linked to entities"
    entity_ids = {row["entity_id"] for row in links}
    assert any(eid.startswith("organization:") for eid in entity_ids)

    # ...and every claim carries its verbatim quote.
    provenance = await orchestrator.kuzu.read(
        "MATCH (c:Claim)-[e:EVIDENCED_BY]->(s:SourceDoc) "
        "RETURN c.claim_id AS claim_id, e.exact_quote AS quote, "
        "e.nli_score AS nli, s.sha256 AS sha"
    )
    assert provenance, "every claim must have an EVIDENCED_BY edge"
    for row in provenance:
        assert row["quote"] in DOC, f"quote is not verbatim: {row['quote']!r}"
        assert row["nli"] >= 0.85


async def test_wiki_dossier_is_written_and_resolvable(orchestrator):
    await orchestrator.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    wiki_dir = orchestrator.wiki_sync.wiki_vault
    files = sorted(wiki_dir.glob("*.md"))
    assert files, "no wiki dossier was written"

    content = files[0].read_text(encoding="utf-8")
    assert content.startswith("---")
    assert "kuzu_id:" in content
    assert "confidence_score:" in content
    assert "last_compiled:" in content

    # The dossier must be reachable through the entity id, not just by filename.
    entity = await orchestrator.wiki_sync.get_entity("organization:acme-corporation")
    assert entity is not None
    dossier = await orchestrator.wiki_sync.read_entity_wiki("organization:acme-corporation")
    assert dossier and dossier.startswith("---")


async def test_dossier_carries_the_source_and_admiralty_rating(orchestrator):
    """The frontmatter claimed F_CANNOT_BE_JUDGED with no sources at all."""
    await orchestrator.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    dossier = await orchestrator.wiki_sync.read_entity_wiki("organization:acme-corporation")
    assert dossier is not None

    import yaml

    frontmatter = yaml.safe_load(dossier.split("---")[1])
    assert frontmatter["sources"], "no source documents recorded in the dossier"
    assert frontmatter["admiralty_rating"].startswith("A")


async def test_dossier_quotes_the_verbatim_source(orchestrator):
    await orchestrator.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    dossier = await orchestrator.wiki_sync.read_entity_wiki("organization:acme-corporation")
    assert dossier is not None
    assert "Acme Corporation manufactures the X-200 drone airframe" in dossier
    assert "entailment" in dossier


async def test_entity_resolution_merges_and_deduplicates(orchestrator):
    """A second mention of the same entity must not create a duplicate node."""
    payload = RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    await orchestrator.ingest_and_compile(payload)

    entities = await orchestrator.kuzu.read("MATCH (e:Entity) RETURN e.canonical_name AS name")
    names = [row["name"].lower() for row in entities]
    assert len(names) == len(set(names)), f"duplicate entities: {names}"


async def test_gatekeeper_marks_the_source_with_admiralty_and_archives_it(orchestrator):
    state = await orchestrator.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    gate = state["gatekeeper_result"]
    assert gate.slop_metrics is not None
    assert gate.slop_metrics.admiralty_reliability.value.startswith("A")

    rows = await orchestrator.kuzu.read(
        "MATCH (s:SourceDoc) RETURN s.sha256 AS sha, s.admiralty_reliability AS admiralty, "
        "s.raw_archive_path AS archive, s.is_quarantined AS quarantined"
    )
    assert rows
    assert rows[0]["quarantined"] is False
    assert rows[0]["archive"]
    assert rows[0]["sha"] == gate.doc_sha256


async def test_swarm_uses_distinct_expert_temperatures(orchestrator):
    await orchestrator.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    temps = sorted(call["temperature"] for call in orchestrator.fake_router.calls)
    assert temps == [0.0, 0.1, 0.2], f"expert temperatures not distinct: {temps}"


async def test_relation_is_rejected_when_the_quote_is_not_grounded(orchestrator):
    """The gate must drop an ungrounded relation even if the swarm proposes it."""
    from kuzuwiki.agents.swarm_extractor import SwarmExtractor

    class GroundednessBreaker(FakeOpenRouter):
        async def chat_completion(self, system_prompt, text, model_override=None, temperature=0.0):
            payload = json.loads(json.dumps(DEFAULT_EXPERT_PAYLOAD))
            payload["relations"][0]["evidence"]["exact_quote"] = (
                "This sentence does not appear anywhere in the source document."
            )
            return {"content": json.dumps(payload)}

    raw = orchestrator.gatekeeper.raw_vault
    orchestrator.swarm = SwarmExtractor(openrouter_client=GroundednessBreaker())
    state = await orchestrator.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    assert state["error"] is None
    assert state["compile_stats"]["relations"] == 1, state["compile_stats"]
    assert raw.exists()
