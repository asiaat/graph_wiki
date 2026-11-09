"""WP-4 gate: the API contract must match what the frontend actually calls.

Historically every router declared ``prefix="/api/v1/x"`` *and* ``main.py``
added the same prefix again, so the live path was
``/api/v1/graph/api/v1/graph/subgraph`` and 100% of frontend calls 404'd.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from kuzuwiki.main import app

#: The paths the frontend calls (frontend/src/services/apiClient.ts).
FRONTEND_EXPECTED = {
    ("GET", "/api/v1/projects"),
    ("POST", "/api/v1/projects"),
    ("POST", "/api/v1/projects/{project_id}/archive"),
    ("POST", "/api/v1/projects/{project_id}/restore"),
    ("DELETE", "/api/v1/projects/{project_id}"),
    ("PUT", "/api/v1/projects/{project_id}/dashboard"),
    ("GET", "/api/v1/projects/{project_id}/entities"),
    ("GET", "/api/v1/projects/{project_id}/links"),
    ("POST", "/api/v1/projects/{project_id}/links"),
    ("DELETE", "/api/v1/projects/{project_id}/links/{link_id}"),
    ("POST", "/api/v1/ingest/document"),
    ("GET", "/api/v1/ingest/documents"),
    ("GET", "/api/v1/ingest/documents/{doc_sha256}/content"),
    ("POST", "/api/v1/graph/subgraph"),
    ("POST", "/api/v1/graph/shortest-path"),
    ("POST", "/api/v1/graph/clusters"),
    ("GET", "/api/v1/graph/entity/{entity_id}"),
    ("GET", "/api/v1/wiki/{slug}"),
    ("GET", "/api/v1/wiki/entity/{entity_id}"),
    ("PUT", "/api/v1/wiki/{slug}"),
    ("POST", "/api/v1/osint/complicate/{entity_id}"),
    ("GET", "/api/v1/osint/attack-index"),
    ("GET", "/api/v1/osint/lint/contradictions"),
    ("POST", "/api/v1/query/compiled"),
    ("GET", "/api/v1/osint/gap-tickets"),
    ("POST", "/api/v1/osint/gap-tickets/review"),
}


def _live_routes() -> set[tuple[str, str]]:
    """Enumerate the public contract from the OpenAPI schema.

    FastAPI 0.143 keeps included routers behind an ``_IncludedRouter``
    wrapper, so ``app.routes`` no longer exposes the individual routes - the
    generated OpenAPI document is the authoritative view of what a client can
    actually call.
    """
    routes: set[tuple[str, str]] = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                routes.add((method.upper(), path))
    return routes


def test_live_routes_cover_every_frontend_call():
    live = _live_routes()
    missing = FRONTEND_EXPECTED - live
    assert not missing, f"frontend calls routes that do not exist: {sorted(missing)}"


def test_no_double_prefixed_routes():
    """The old bug produced paths like /api/v1/graph/api/v1/graph/subgraph."""
    live = _live_routes()
    doubled = [path for _, path in live if path.count("/api/v1") > 1]
    assert not doubled, f"double-prefixed routes: {doubled}"


def test_openapi_documents_the_expected_paths():
    schema = app.openapi()
    paths = set(schema["paths"])
    for _, expected in FRONTEND_EXPECTED:
        assert expected in paths, f"{expected} missing from OpenAPI"


def test_health_endpoint_is_public():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.fixture
def started_client(tmp_path, monkeypatch):
    """A client whose lifespan runs against a scratch database."""
    from kuzuwiki.config import settings
    from kuzuwiki.db.kuzu_client import KuzuClient

    db_path = tmp_path / "kuzudb"
    db_path.mkdir(exist_ok=True)
    # KùzuDB needs a *file* path, not a directory.
    monkeypatch.setattr(settings, "kuzu_db_path", str(db_path / "graph.kuzu"))
    monkeypatch.setattr(settings, "wiki_vault_path", str(tmp_path / "wiki"))
    monkeypatch.setattr(settings, "raw_vault_path", str(tmp_path / "raw"))
    monkeypatch.setattr(settings, "project_data_root", str(tmp_path / "projects"))
    (tmp_path / "wiki").mkdir(exist_ok=True)
    (tmp_path / "raw").mkdir(exist_ok=True)

    with TestClient(app) as client:
        yield client
    KuzuClient._shared_instance = None


def test_lifespan_creates_the_schema(started_client):
    tables = started_client.get("/api/v1/osint/attack-index")
    assert tables.status_code == 200, tables.text
    assert "time_series" in tables.json()


def test_lifespan_wires_the_orchestrator(started_client):
    """``app.state.orchestrator`` was read but never assigned."""
    from kuzuwiki.main import app as fastapi_app

    assert hasattr(fastapi_app.state, "orchestrator")
    assert hasattr(fastapi_app.state, "wiki_sync")
    assert hasattr(fastapi_app.state, "kuzu")


def test_empty_project_can_be_archived_restored_and_deleted_via_api(started_client):
    from pathlib import Path

    created = started_client.post("/api/v1/projects", json={"name": "Empty project"})
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    archived = started_client.post(f"/api/v1/projects/{project_id}/archive")
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"]
    active = started_client.get("/api/v1/projects").json()["projects"]
    assert project_id not in {project["id"] for project in active}
    all_projects = started_client.get("/api/v1/projects", params={"include_archived": "true"}).json()["projects"]
    assert project_id in {project["id"] for project in all_projects}

    restored = started_client.post(f"/api/v1/projects/{project_id}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived_at"] is None

    async def open_project_runtime():
        await started_client.app.state.project_manager.get(project_id)

    asyncio.run(open_project_runtime())
    project_data = Path(started_client.app.state.project_store.path).parent / project_id
    project_data.mkdir(parents=True, exist_ok=True)
    (project_data / "source-marker.txt").write_text("project data", encoding="utf-8")

    deleted = started_client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 204, deleted.text
    assert not project_data.exists(), "Project deletion left its isolated graph/vault directory behind"
    assert project_id not in {project["id"] for project in started_client.get("/api/v1/projects").json()["projects"]}


def test_default_project_cannot_be_archived_or_deleted(started_client):
    assert started_client.post("/api/v1/projects/default/archive").status_code == 422
    assert started_client.delete("/api/v1/projects/default").status_code == 422


def test_source_text_preview_is_project_scoped_and_hash_validated(started_client):
    from pathlib import Path

    sha256 = "a" * 64
    raw_vault = Path(started_client.app.state.orchestrator.gatekeeper.raw_vault)
    (raw_vault / f"{sha256}.txt").write_text("Extracted PDF text", encoding="utf-8")

    preview = started_client.get(f"/api/v1/ingest/documents/{sha256}/content")
    assert preview.status_code == 200, preview.text
    assert preview.text == "Extracted PDF text"

    invalid = started_client.get("/api/v1/ingest/documents/not-a-hash/content")
    assert invalid.status_code == 400


def test_projects_have_isolated_graphs_and_persist_dashboard_layout(started_client):
    default_kuzu = started_client.app.state.kuzu
    asyncio.run(
        default_kuzu.write(
            "CREATE (e:Entity {id: 'default-only', canonical_name: 'Default only'})"
        )
    )

    created = started_client.post("/api/v1/projects", json={"name": "Alpha Study"})
    assert created.status_code == 201, created.text
    project = created.json()
    project_id = project["id"]
    assert project["dashboard_layout"]["panels"]

    isolated_count = started_client.get(
        "/api/v1/graph/entities/count", headers={"X-Project-ID": project_id}
    )
    assert isolated_count.status_code == 200, isolated_count.text
    assert isolated_count.json()["total"] == 0

    default_count = started_client.get("/api/v1/graph/entities/count")
    assert default_count.status_code == 200, default_count.text
    assert default_count.json()["total"] == 1

    layout = {
        "version": 1,
        "panels": [{"id": "attack-index", "width": "wide"}],
    }
    saved = started_client.put(
        f"/api/v1/projects/{project_id}/dashboard", json=layout
    )
    assert saved.status_code == 200, saved.text
    listed = started_client.get("/api/v1/projects")
    saved_project = next(item for item in listed.json()["projects"] if item["id"] == project_id)
    assert saved_project["dashboard_layout"] == layout

    second_project = started_client.post("/api/v1/projects", json={"name": "Beta Study"})
    assert second_project.status_code == 201, second_project.text
    second_project_id = second_project.json()["id"]

    async def seed_project_entities():
        manager = started_client.app.state.project_manager
        left_runtime = await manager.get(project_id)
        right_runtime = await manager.get(second_project_id)
        await left_runtime.kuzu.write(
            "CREATE (e:Entity {id: 'alpha-entity', canonical_name: 'Alpha Entity'})"
        )
        await right_runtime.kuzu.write(
            "CREATE (e:Entity {id: 'beta-entity', canonical_name: 'Beta Entity'})"
        )

    asyncio.run(seed_project_entities())
    linked = started_client.post(
        f"/api/v1/projects/{project_id}/links",
        json={
            "source_entity_id": "alpha-entity",
            "target_project_id": second_project_id,
            "target_entity_id": "beta-entity",
            "link_kind": "possible_match",
            "rationale": "Check primary identifiers in both projects.",
        },
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["link"]["to_entity_name"] == "Beta Entity"
    target_links = started_client.get(f"/api/v1/projects/{second_project_id}/links")
    assert target_links.status_code == 200, target_links.text
    assert target_links.json()["links"][0]["from_entity_name"] == "Alpha Entity"


def test_graph_entity_returns_json_serialisable_payload(started_client):
    response = started_client.get("/api/v1/graph/entity/organization:nope")
    assert response.status_code == 404


def test_graph_entity_picker_prioritizes_connected_entities(started_client):
    _seed_claim(started_client)

    response = started_client.get("/api/v1/graph/entities")

    assert response.status_code == 200, response.text
    entities = response.json()["entities"]
    assert [entity["id"] for entity in entities[:2]] == [
        "organization:acme",
        "organization:beta",
    ]
    assert all(entity["relation_count"] == 1 for entity in entities[:2])


def test_wiki_map_returns_dossiers_and_cited_relationships(started_client):
    _seed_claim(started_client)

    response = started_client.get("/api/v1/graph/wiki-map")

    assert response.status_code == 200, response.text
    body = response.json()
    assert {entity["id"] for entity in body["entities"]} == {
        "organization:acme",
        "organization:beta",
    }
    assert len(body["edges"]) == 1
    assert body["edges"][0]["evidence"][0]["exact_quote"].startswith(
        "Acme Corporation manufactures"
    )


def test_lint_contradictions_returns_serialisable_results(started_client):
    """Raw Kùzu node objects used to make this endpoint 500."""
    response = started_client.get("/api/v1/osint/lint/contradictions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"contradictions", "decay_issues", "wave_alerts", "structural_gaps"}


def _seed_claim(
    client: TestClient,
    *,
    claim_id: str = "claim-acme",
    confidence: float = 0.92,
    entailment: float = 0.96,
    quote: str = "Acme Corporation manufactures the X-200 drone airframe for Beta Systems.",
) -> None:
    """Seed one grounded graph claim for query and graph-view route checks."""
    kuzu = client.app.state.kuzu
    statements = [
        (
            "MERGE (e:Entity {id: $id}) SET e.canonical_name = $name, "
            "e.category = 'Organization', e.slug = $slug, e.summary = $summary, "
            "e.confidence_score = 0.9",
            {
                "id": "organization:acme",
                "name": "Acme Corporation",
                "slug": "acme-corporation",
                "summary": "A manufacturer of the X-200 airframe.",
            },
        ),
        (
            "MERGE (e:Entity {id: $id}) SET e.canonical_name = $name, "
            "e.category = 'Organization', e.slug = $slug, e.summary = $summary, "
            "e.confidence_score = 0.88",
            {
                "id": "organization:beta",
                "name": "Beta Systems",
                "slug": "beta-systems",
                "summary": "A systems company.",
            },
        ),
        (
            "MERGE (s:SourceDoc {sha256: $sha}) SET s.title = $title, s.uri = $uri, "
            "s.admiralty_reliability = $rating, s.credibility_rank = 2",
            {
                "sha": "source-acme-001",
                "title": "Acme supply report",
                "uri": "https://example.test/acme-report",
                "rating": "A_COMPLETELY_RELIABLE",
            },
        ),
        (
            "MERGE (c:Claim {claim_id: $claim_id}) SET c.statement = $statement, "
            "c.confidence = $confidence, c.nli_entailment = $entailment, "
            "c.swarm_votes = 2, c.status = 'CORROBORATED', c.predicate = 'MANUFACTURES'",
            {
                "claim_id": claim_id,
                "statement": "Acme Corporation MANUFACTURES Beta Systems",
                "confidence": confidence,
                "entailment": entailment,
            },
        ),
        (
            "MATCH (c:Claim {claim_id: $claim_id}) MATCH (e:Entity {id: $entity_id}) "
            "MERGE (c)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e)",
            {"claim_id": claim_id, "entity_id": "organization:acme"},
        ),
        (
            "MATCH (c:Claim {claim_id: $claim_id}) MATCH (s:SourceDoc {sha256: $sha}) "
            "MERGE (c)-[ev:EVIDENCED_BY]->(s) SET ev.exact_quote = $quote, "
            "ev.nli_score = $entailment, ev.start_char = 0, ev.end_char = $end_char",
            {
                "claim_id": claim_id,
                "sha": "source-acme-001",
                "quote": quote,
                "entailment": entailment,
                "end_char": len(quote),
            },
        ),
        (
            "MATCH (a:Entity {id: $source}) MATCH (b:Entity {id: $target}) "
            "MERGE (a)-[r:RELATES_TO {relation_type: 'MANUFACTURES'}]->(b) "
            "SET r.weight = $weight, r.claim_id = $claim_id, r.is_disputed = false",
            {
                "source": "organization:acme",
                "target": "organization:beta",
                "weight": confidence,
                "claim_id": claim_id,
            },
        ),
    ]
    for statement, params in statements:
        asyncio.run(kuzu.write(statement, params))


def test_compiled_query_returns_claim_with_source_and_can_file_synthesis(started_client):
    _seed_claim(started_client)

    response = started_client.post(
        "/api/v1/query/compiled",
        json={
            "question": "What does Acme manufacture?",
            "entity_id": "organization:acme",
            "save_to_wiki": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ANSWERED"
    assert body["verified_claim_count"] == 1
    finding = body["findings"][0]
    assert finding["quote"].startswith("Acme Corporation manufactures")
    assert finding["source_sha256"] == "source-acme-001"
    assert finding["confidence"] >= 0.70
    assert finding["entailment"] >= 0.85
    assert body["filed_synthesis_id"]

    linked = asyncio.run(
        started_client.app.state.kuzu.read(
            "MATCH (:Entity {id: 'organization:acme'})-[:SYNTHESIS_FOR]->(c:Concept) "
            "RETURN c.id AS id"
        )
    )
    assert linked and linked[0]["id"] == body["filed_synthesis_id"]


def test_compiled_query_declines_weak_claim_and_opens_reviewable_gap(started_client):
    _seed_claim(started_client, confidence=0.62)

    response = started_client.post(
        "/api/v1/query/compiled",
        json={"question": "What does Acme manufacture?", "entity_id": "organization:acme"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert body["findings"] == []
    assert body["gap_ticket_id"]
    tickets = started_client.get("/api/v1/osint/gap-tickets?status=OPEN").json()["tickets"]
    assert any(ticket["ticket_id"] == body["gap_ticket_id"] for ticket in tickets)


def test_compiled_query_does_not_present_unresolved_contradictions(started_client):
    _seed_claim(started_client)
    kuzu = started_client.app.state.kuzu
    statements = [
        (
            "MERGE (c:Claim {claim_id: 'claim-conflict'}) "
            "SET c.statement = 'Acme Corporation DOES_NOT_MANUFACTURE Beta Systems', "
            "c.confidence = 0.9, c.nli_entailment = 0.96, c.swarm_votes = 2, "
            "c.predicate = 'MANUFACTURES', c.status = 'CORROBORATED'"
        ),
        (
            "MATCH (c:Claim {claim_id: 'claim-conflict'}) "
            "MATCH (e:Entity {id: 'organization:acme'}) "
            "MERGE (c)-[:ASSERTS_ABOUT {role: 'SUBJECT'}]->(e)"
        ),
        (
            "MATCH (a:Claim {claim_id: 'claim-acme'}) "
            "MATCH (b:Claim {claim_id: 'claim-conflict'}) "
            "MERGE (a)-[:CONTRADICTS]->(b)"
        ),
    ]
    for statement in statements:
        asyncio.run(kuzu.write(statement))

    response = started_client.post(
        "/api/v1/query/compiled",
        json={"question": "What does Acme manufacture?", "entity_id": "organization:acme"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    assert response.json()["findings"] == []


def test_graph_subgraph_and_wiki_expose_directed_relation_evidence(started_client):
    _seed_claim(started_client)

    response = started_client.post(
        "/api/v1/graph/subgraph",
        json={"entity_id": "organization:acme", "hops": 1},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    edge = next(edge for edge in body["edges"] if edge["relation_type"] == "MANUFACTURES")
    assert edge["source"] == "organization:acme"
    assert edge["target"] == "organization:beta"
    assert edge["evidence"][0]["source_sha256"] == "source-acme-001"
    assert "Acme Corporation manufactures" in edge["evidence"][0]["exact_quote"]

    dossier = asyncio.run(
        started_client.app.state.wiki_sync._entity_document(
            {"id": "organization:acme", "canonical_name": "Acme Corporation"}
        )
    )
    assert "## Relations" in dossier
    assert "[[beta-systems|Beta Systems]]" in dossier
    assert "Source SHA-256: `source-acme-001`" in dossier
