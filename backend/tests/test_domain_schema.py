"""WP-6 gate: the domain schema layer, Lande persistence and reprint cascade.

These three were the last pieces of the system that were specified but never
wired up: the domain packs were never loaded, the visibility graph was
computed and then discarded, and reprint detection could never fire because
the gatekeeper never handed it any document content.
"""

from __future__ import annotations

from kuzuwiki.jev.schemas import RawDocumentPayload
from kuzuwiki.lande.domain_schema import load_all_schemas, load_schema, schema_dir
from kuzuwiki.lande.hvg_network import compute_hvg
from kuzuwiki.lande.reprint_cascade import (
    compute_influence_delay,
    detect_reprint,
    jaccard_similarity,
    minhash_signature,
)

from .conftest import SAMPLE_DOC as DOC

# ---------------------------------------------------------------- domain packs


def test_domain_packs_are_discovered():
    directory = schema_dir()
    assert directory is not None, "no domain schema directory found"
    schemas = load_all_schemas()
    assert schemas, "no domain packs were loaded"
    assert "drone_supply_chain" in schemas
    assert "hybrid_warfare" in schemas
    assert "corporate_osint" in schemas


def test_domain_pack_defines_the_governance_fields():
    schema = load_schema("drone_supply_chain")
    assert schema is not None
    assert schema.lande_stopwords
    assert schema.entity_types
    assert schema.edge_types
    assert schema.osint_templates
    assert schema.attack_index.wave_threshold_sigma == 2.5
    assert schema.attack_index.reprint_threshold == 0.85


def test_domain_pack_renders_osint_dorks():
    schema = load_schema("drone_supply_chain")
    dorks = schema.dorks_for("Acme Corporation")
    assert dorks
    assert any("Acme Corporation" in d for d in dorks)


def test_unknown_domain_returns_none():
    assert load_schema("does-not-exist") is None


# ----------------------------------------------------------------- HVG / Lande


def test_hub_terms_exclude_stopwords():
    text = (
        "The unit and the drone were used in the attack. The drone unit was "
        "attacked by the unit. And the drone, the unit, the attack."
    )
    from kuzuwiki.jev.textutil import STOPWORDS

    result = compute_hvg(text)
    assert result.hub_terms, "no hub terms were produced"
    for term in result.hub_terms:
        assert term not in STOPWORDS, f"stopword '{term}' leaked into the hub terms"


def test_hvg_weights_are_not_degenerate():
    """The old IDF made every weight negative, inverting prominence."""
    text = "drone drone drone rotor rotor frame frame battery"
    result = compute_hvg(text)
    assert result.term_weights
    assert all(weight > 0 for weight in result.term_weights.values())
    assert result.term_weights["drone"] > result.term_weights["battery"]


def test_hvg_visibility_rule_is_respected():
    text = "alpha alpha alpha beta gamma delta epsilon zeta"
    result = compute_hvg(text)
    assert result.edges
    assert any(edge.term_a == "alpha" or edge.term_b == "alpha" for edge in result.edges)


def test_hvg_is_linear_not_quadratic():
    """A long document must not blow up the edge construction."""
    import time

    text = " ".join(["drone rotor frame battery payload avionics"] * 400)
    start = time.perf_counter()
    result = compute_hvg(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"HVG took {elapsed:.2f}s"
    assert result.hub_terms


# ----------------------------------------------------------- reprint cascade


def test_minhash_detects_identical_text():
    text = "The quick brown fox jumps over the lazy dog. " * 20
    sig_a = minhash_signature(text)
    sig_b = minhash_signature(text)
    assert jaccard_similarity(sig_a, sig_b) == 1.0


def test_detect_reprint_requires_content():
    """Before the fix the gatekeeper passed no content, so nothing ever matched."""
    content = "Acme Corporation manufactures drones for Beta Systems. " * 10
    candidates = [
        {"sha256": "abc", "content": content},
        {"sha256": "def", "content": "Something entirely different about widgets. " * 10},
    ]
    is_reprint, sha, score = detect_reprint(content, candidates)
    assert is_reprint
    assert sha == "abc"
    assert score >= 0.85


def test_detect_reprint_reads_the_archived_copy(tmp_path):
    """The archive path is resolved against the raw vault."""
    content = "Acme Corporation manufactures drones for Beta Systems. " * 10
    archive = tmp_path / "sha1.txt"
    archive.write_text(content, encoding="utf-8")

    candidates = [{"sha256": "sha1", "archive_path": str(archive)}]
    is_reprint, sha, _ = detect_reprint(content, candidates, archive_root=tmp_path)
    assert is_reprint
    assert sha == "sha1"


def test_influence_delay_is_computed_from_timestamps():
    from datetime import datetime, timezone

    t0 = datetime(2024, 3, 1, tzinfo=timezone.utc)
    t1 = datetime(2024, 3, 1, 2, 0, tzinfo=timezone.utc)
    assert compute_influence_delay(t0, t1) == 7200
    assert compute_influence_delay(None, t1) == 0
    assert compute_influence_delay(t0, "not-a-date") == 0


# ------------------------------------------------------ graph-level behaviour


async def test_term_hierarchy_is_persisted(orchestrator, graph):
    orch = orchestrator
    state = await orch.ingest_and_compile(
        RawDocumentPayload(content=DOC, title="Report", domain="reuters.com")
    )
    assert state["error"] is None, state["error"]
    assert state["compile_stats"]["terms"] > 0

    terms = await graph.read(
        "MATCH (t:DomainTerm) RETURN t.term AS term, t.idf_weight AS weight, t.hvg_degree AS degree"
    )
    assert terms, "no DomainTerm nodes were persisted"
    assert all(t["weight"] > 0 for t in terms)


async def test_reprint_creates_a_cascade_edge(orchestrator, graph):
    orch = orchestrator
    payload = RawDocumentPayload(
        content=DOC,
        title="Report",
        domain="reuters.com",
        published_at="2024-03-12",
    )
    await orch.ingest_and_compile(payload)

    # A second outlet republishes the same text.
    reprint = RawDocumentPayload(
        content=DOC,
        title="Report (reprint)",
        domain="example.com",
        published_at="2024-03-13",
    )
    state = await orch.ingest_and_compile(reprint)
    assert state["error"] is None, state["error"]
    gate = state["gatekeeper_result"]
    assert gate.is_reprint, "the reprint was not detected"
    assert gate.reprint_of

    edges = await graph.read(
        "MATCH (a:SourceDoc)-[r:REPRINTS_FROM]->(b:SourceDoc) "
        "RETURN a.domain AS source, b.domain AS original, "
        "r.similarity_score AS similarity, r.lag_seconds AS lag"
    )
    assert edges, "no REPRINTS_FROM edge was created"
    assert edges[0]["original"] == "reuters.com"
    assert edges[0]["similarity"] >= 0.85
    assert edges[0]["lag"] == 86400
