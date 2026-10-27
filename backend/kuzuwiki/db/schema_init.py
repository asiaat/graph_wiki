"""KùzuDB schema definition and idempotent DDL execution.

Kùzu 0.11.x specifics that shape this module:

* ``CREATE NODE TABLE`` / ``CREATE REL TABLE`` support ``IF NOT EXISTS``;
  scalar ``CREATE INDEX`` is *not* supported as a statement (indexes are
  implicit), so we only manage the extension-backed indexes.
* Full-text indexes are created with ``CALL create_fts_index(table, name, cols)``
  and require the ``fts`` extension.
* Vector (HNSW) indexes are created with ``CALL create_vector_index(table, name, col)``
  and require the ``vector`` extension.
* ``INSTALL <ext>`` downloads the extension, so it needs network access. Both
  extension steps are best-effort: the core relational schema must come up even
  on an air-gapped host.
"""

from __future__ import annotations

import logging
from typing import Any

from kuzuwiki.db.kuzu_client import KuzuClient

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Core relational schema
# --------------------------------------------------------------------------

NODE_TABLES: list[tuple[str, str]] = [
    (
        "SourceDoc",
        """
        CREATE NODE TABLE IF NOT EXISTS SourceDoc (
            sha256 STRING,
            uri STRING,
            title STRING,
            domain STRING,
            published_at TIMESTAMP,
            ingested_at TIMESTAMP,
            admiralty_reliability STRING,
            credibility_rank INT64,
            slop_score DOUBLE,
            attack_index DOUBLE,
            raw_archive_path STRING,
            primary_term STRING,
            is_quarantined BOOLEAN,
            quarantined_reason STRING,
            PRIMARY KEY (sha256)
        )
        """,
    ),
    (
        "Entity",
        """
        CREATE NODE TABLE IF NOT EXISTS Entity (
            id STRING,
            slug STRING,
            canonical_name STRING,
            category STRING,
            aliases STRING[],
            external_ids JSON,
            summary STRING,
            wiki_markdown STRING,
            confidence_score DOUBLE,
            lifecycle_state STRING,
            hvg_centrality DOUBLE,
            embedding DOUBLE[1024],
            updated_at TIMESTAMP,
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "Claim",
        """
        CREATE NODE TABLE IF NOT EXISTS Claim (
            claim_id STRING,
            statement STRING,
            predicate STRING,
            valid_from TIMESTAMP,
            valid_to TIMESTAMP,
            confidence DOUBLE,
            nli_entailment DOUBLE,
            swarm_votes INT64,
            status STRING,
            embedding DOUBLE[1024],
            PRIMARY KEY (claim_id)
        )
        """,
    ),
    (
        "Concept",
        """
        CREATE NODE TABLE IF NOT EXISTS Concept (
            id STRING,
            slug STRING,
            name STRING,
            definition STRING,
            wiki_markdown STRING,
            confidence_score DOUBLE,
            updated_at TIMESTAMP,
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "DomainTerm",
        """
        CREATE NODE TABLE IF NOT EXISTS DomainTerm (
            term STRING,
            idf_weight DOUBLE,
            hvg_degree INT64,
            burst_score DOUBLE,
            PRIMARY KEY (term)
        )
        """,
    ),
    (
        "NarrativeWave",
        """
        CREATE NODE TABLE IF NOT EXISTS NarrativeWave (
            wave_id STRING,
            term STRING,
            started_at TIMESTAMP,
            peak_at TIMESTAMP,
            magnitude DOUBLE,
            sigma DOUBLE,
            trigger_type STRING,
            doc_count INT64,
            PRIMARY KEY (wave_id)
        )
        """,
    ),
    (
        "ComplicationTicket",
        """
        CREATE NODE TABLE IF NOT EXISTS ComplicationTicket (
            ticket_id STRING,
            target_entity_id STRING,
            gap_type STRING,
            hypothesis_query STRING,
            generated_dorks STRING[],
            status STRING,
            created_at TIMESTAMP,
            PRIMARY KEY (ticket_id)
        )
        """,
    ),
    (
        "OSINTGapTicket",
        """
        CREATE NODE TABLE IF NOT EXISTS OSINTGapTicket (
            ticket_id STRING,
            target_entity_id STRING,
            gap_description STRING,
            required_evidence STRING,
            confidence_threshold DOUBLE,
            status STRING,
            created_at TIMESTAMP,
            PRIMARY KEY (ticket_id)
        )
        """,
    ),
    (
        "CognitiveOperationAlert",
        """
        CREATE NODE TABLE IF NOT EXISTS CognitiveOperationAlert (
            alert_id STRING,
            wave_id STRING,
            severity DOUBLE,
            summary STRING,
            status STRING,
            detected_at TIMESTAMP,
            PRIMARY KEY (alert_id)
        )
        """,
    ),
    (
        "AgentTask",
        """
        CREATE NODE TABLE IF NOT EXISTS AgentTask (
            task_id STRING,
            task_type STRING,
            status STRING,
            params STRING,
            created_at TIMESTAMP,
            PRIMARY KEY (task_id)
        )
        """,
    ),
]


REL_TABLES: list[tuple[str, str]] = [
    (
        "RELATES_TO",
        """
        CREATE REL TABLE IF NOT EXISTS RELATES_TO (
            FROM Entity TO Entity,
            relation_type STRING,
            weight DOUBLE,
            valid_from TIMESTAMP,
            valid_to TIMESTAMP,
            claim_id STRING,
            is_disputed BOOLEAN
        )
        """,
    ),
    (
        "EVIDENCED_BY",
        """
        CREATE REL TABLE IF NOT EXISTS EVIDENCED_BY (
            FROM Claim TO SourceDoc,
            exact_quote STRING,
            start_char INT64,
            end_char INT64,
            nli_score DOUBLE,
            extracted_by_swarm_run STRING
        )
        """,
    ),
    (
        "ASSERTS_ABOUT",
        """
        CREATE REL TABLE IF NOT EXISTS ASSERTS_ABOUT (
            FROM Claim TO Entity,
            role STRING
        )
        """,
    ),
    (
        "CONTRADICTS",
        """
        CREATE REL TABLE IF NOT EXISTS CONTRADICTS (
            FROM Claim TO Claim,
            contradiction_type STRING,
            severity DOUBLE,
            detected_at TIMESTAMP,
            resolution_notes STRING
        )
        """,
    ),
    (
        "REPRINTS_FROM",
        """
        CREATE REL TABLE IF NOT EXISTS REPRINTS_FROM (
            FROM SourceDoc TO SourceDoc,
            similarity_score DOUBLE,
            lag_seconds INT64
        )
        """,
    ),
    (
        "TERMS_RELATE_TO",
        """
        CREATE REL TABLE IF NOT EXISTS TERMS_RELATE_TO (
            FROM DomainTerm TO Entity,
            weight DOUBLE,
            centrality DOUBLE
        )
        """,
    ),
    (
        "TERM_DOMINATES",
        """
        CREATE REL TABLE IF NOT EXISTS TERM_DOMINATES (
            FROM DomainTerm TO DomainTerm,
            visibility_weight DOUBLE,
            directional_asymmetry DOUBLE
        )
        """,
    ),
    (
        "WAVE_MENTIONS",
        """
        CREATE REL TABLE IF NOT EXISTS WAVE_MENTIONS (
            FROM NarrativeWave TO SourceDoc,
            contribution DOUBLE
        )
        """,
    ),
    (
        "TARGETS",
        """
        CREATE REL TABLE IF NOT EXISTS TARGETS (
            FROM ComplicationTicket TO Entity,
            gap_type STRING
        )
        """,
    ),
]


# (index_name, table, columns) - BM25 style full-text
FTS_INDEXES: list[tuple[str, str, list[str]]] = [
    ("claim_statement_ft", "Claim", ["statement"]),
    ("entity_summary_ft", "Entity", ["summary"]),
]

# (index_name, table, column) - HNSW cosine vector
VECTOR_INDEXES: list[tuple[str, str, str]] = [
    ("entity_embedding_hnsw", "Entity", "embedding"),
    ("claim_embedding_hnsw", "Claim", "embedding"),
]


async def _load_extension(client: KuzuClient, extension: str) -> bool:
    """Install and load a Kùzu extension. Returns False when unavailable."""
    for statement in (f"INSTALL {extension}", f"LOAD {extension}"):
        try:
            await client.write(statement)
        except Exception as exc:
            logger.warning(
                "Kùzu extension %r unavailable (%s); dependent indexes are skipped",
                extension,
                exc,
            )
            return False
    return True


async def _existing_indexes(client: KuzuClient) -> set[str]:
    rows = await client.read("CALL show_indexes() RETURN *")
    names: set[str] = set()
    for row in rows:
        name = row.get("index_name")
        if isinstance(name, str):
            names.add(name)
    return names


async def ensure_schema(client: KuzuClient) -> dict[str, list[str]]:
    """Create every table and index the system needs. Safe to call repeatedly."""
    created_tables: list[str] = []
    created_indexes: list[str] = []

    for name, ddl in NODE_TABLES + REL_TABLES:
        try:
            await client.write(ddl)
            created_tables.append(name)
        except Exception as exc:
            logger.error("Failed to create table %s: %s", name, exc)
            raise

    existing = await _existing_indexes(client)

    if await _load_extension(client, "fts"):
        for index_name, table, columns in FTS_INDEXES:
            if index_name in existing:
                continue
            try:
                await client.write(f"CALL create_fts_index('{table}', '{index_name}', {columns!r})")
                created_indexes.append(index_name)
            except Exception as exc:
                logger.warning("Could not create FTS index %s: %s", index_name, exc)

    if await _load_extension(client, "vector"):
        for index_name, table, column in VECTOR_INDEXES:
            if index_name in existing:
                continue
            try:
                await client.write(
                    f"CALL create_vector_index('{table}', '{index_name}', '{column}')"
                )
                created_indexes.append(index_name)
            except Exception as exc:
                logger.warning("Could not create vector index %s: %s", index_name, exc)

    logger.info(
        "Kùzu schema ensured: %d tables, %d indexes", len(created_tables), len(created_indexes)
    )
    return {"tables": created_tables, "indexes": created_indexes}


async def schema_status(client: KuzuClient) -> dict[str, Any]:
    """Report which of the declared tables exist in the live database."""
    live_tables = await client.table_names()
    live_indexes = await client.index_names()
    declared = {name for name, _ in NODE_TABLES + REL_TABLES}
    return {
        "tables_present": sorted(declared & live_tables),
        "tables_missing": sorted(declared - live_tables),
        "indexes_present": sorted(live_indexes),
    }
