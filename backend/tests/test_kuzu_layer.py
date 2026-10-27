"""WP-3 gate: the KùzuDB access layer and schema must be real.

Historically this layer was written against a fictional API (``kuzudb`` package,
``KuzuDB.get_instance``, ``cypher_query``, ``read_only_cypher_query``,
``commit``), the DDL never executed, and every write was silently dropped.
These tests pin the real behaviour.
"""

from __future__ import annotations

import pytest

from kuzuwiki.db.kuzu_client import KuzuClient, KuzuError
from kuzuwiki.db.schema_init import NODE_TABLES, REL_TABLES, ensure_schema, schema_status


@pytest.fixture
async def client(kuzu_db_path: str):
    c = await KuzuClient.init(kuzu_db_path)
    try:
        yield c
    finally:
        await c.close()
        KuzuClient._shared_instance = None


async def test_schema_is_created_on_a_fresh_database(client: KuzuClient):
    """A fresh DB must get the schema - the old code returned early here."""
    await ensure_schema(client)
    status = await schema_status(client)
    assert status["tables_missing"] == [], f"missing tables: {status['tables_missing']}"
    assert status["tables_present"], "no tables were created"


async def test_ensure_schema_is_idempotent(client: KuzuClient):
    await ensure_schema(client)
    await ensure_schema(client)
    status = await schema_status(client)
    assert status["tables_missing"] == []


async def test_declared_tables_all_exist(client: KuzuClient):
    await ensure_schema(client)
    live = await client.table_names()
    for name, _ in NODE_TABLES + REL_TABLES:
        assert name in live, f"{name} missing from live database"


async def test_write_then_read_roundtrip(client: KuzuClient):
    await ensure_schema(client)
    await client.write(
        "MERGE (e:Entity {id: $id}) SET e.canonical_name = $name, e.confidence_score = $conf",
        {"id": "organization:acme", "name": "Acme Corp", "conf": 0.91},
    )
    rows = await client.read(
        "MATCH (e:Entity {id: $id}) RETURN e.canonical_name AS name, e.confidence_score AS conf",
        {"id": "organization:acme"},
    )
    assert rows == [{"name": "Acme Corp", "conf": 0.91}]


async def test_awaiting_a_write_guarantees_it_landed(client: KuzuClient):
    """Fire-and-forget queues silently dropped writes; writes must be durable."""
    await ensure_schema(client)
    await client.write(
        "MERGE (d:SourceDoc {sha256: $sha}) SET d.title = $title", {"sha": "abc", "title": "Report"}
    )
    rows = await client.read("MATCH (d:SourceDoc) RETURN count(d) AS n")
    assert rows[0]["n"] == 1


async def test_rows_are_json_serializable_dicts(client: KuzuClient):
    """Raw Kuzu node objects used to leak into FastAPI responses and 500."""
    import json

    await ensure_schema(client)
    await client.write(
        "MERGE (e:Entity {id: $id}) SET e.canonical_name = $n", {"id": "x", "n": "X"}
    )
    rows = await client.read("MATCH (e:Entity) RETURN e")
    json.dumps(rows)
    assert isinstance(rows[0]["e"], dict)


async def test_failed_statement_raises(client: KuzuClient):
    await ensure_schema(client)
    with pytest.raises(KuzuError):
        await client.read("MATCH (n:NoSuchTable) RETURN n")


async def test_timestamp_parameters_must_be_datetime(client: KuzuClient):
    """ISO strings are rejected by the binder - they must be converted upstream."""
    import datetime

    await ensure_schema(client)
    await client.write(
        "MERGE (d:SourceDoc {sha256: $sha}) SET d.published_at = $ts",
        {"sha": "t1", "ts": datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)},
    )
    rows = await client.read("MATCH (d:SourceDoc {sha256: 't1'}) RETURN d.published_at AS ts")
    assert rows[0]["ts"].year == 2024


async def test_fts_index_is_available_for_bm25_search(client: KuzuClient):
    """README claims BM25 full-text search; that needs a real FTS index."""
    await ensure_schema(client)
    await client.write(
        "MERGE (c:Claim {claim_id: $id}) SET c.statement = $s",
        {"id": "c1", "s": "Acme supplies drone propulsion units to Beta"},
    )
    hits = await client.read(
        "CALL query_fts_index('Claim', 'claim_statement_ft', 'drone') RETURN *"
    )
    assert len(hits) >= 1


async def test_vector_index_is_created(client: KuzuClient):
    await ensure_schema(client)
    indexes = await client.index_names()
    assert "entity_embedding_hnsw" in indexes
    assert "claim_embedding_hnsw" in indexes
