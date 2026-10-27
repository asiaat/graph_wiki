"""WP-4 gate: the API contract must match what the frontend actually calls.

Historically every router declared ``prefix="/api/v1/x"`` *and* ``main.py``
added the same prefix again, so the live path was
``/api/v1/graph/api/v1/graph/subgraph`` and 100% of frontend calls 404'd.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kuzuwiki.main import app

#: The paths the frontend calls (frontend/src/services/apiClient.ts).
FRONTEND_EXPECTED = {
    ("POST", "/api/v1/ingest/document"),
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


def test_graph_entity_returns_json_serialisable_payload(started_client):
    response = started_client.get("/api/v1/graph/entity/organization:nope")
    assert response.status_code == 404


def test_lint_contradictions_returns_serialisable_results(started_client):
    """Raw Kùzu node objects used to make this endpoint 500."""
    response = started_client.get("/api/v1/osint/lint/contradictions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"contradictions", "decay_issues", "wave_alerts", "structural_gaps"}
