"""Idempotent KùzuDB DDL execution with index creation."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from kuzudb import KuzuDB

logger = logging.getLogger(__name__)

# DDL statements in dependency order
CREATE_NODE_TABLES = """
-- Immutable Raw Source Document
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
    PRIMARY KEY (sha256)
);

-- Compiled Domain Entity / Wiki Page Node
CREATE NODE TABLE IF NOT EXISTS Entity (
    id STRING,
    canonical_name STRING,
    category STRING,
    aliases STRING[],
    external_ids MAP(STRING, STRING),
    summary STRING,
    wiki_markdown STRING,
    confidence_score DOUBLE,
    lifecycle_state STRING,
    hvg_centrality DOUBLE,
    embedding DOUBLE[1024],
    updated_at TIMESTAMP,
    PRIMARY KEY (id)
);

-- Atomic Fact / Verifiable Claim Node
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
);

-- Lande Term Node (Natural Hierarchy of Terms)
CREATE NODE TABLE IF NOT EXISTS DomainTerm (
    term STRING,
    idf_weight DOUBLE,
    hvg_degree INT64,
    burst_score DOUBLE,
    PRIMARY KEY (term)
);

-- Autonomous Complication / OSINT Research Ticket
CREATE NODE TABLE IF NOT EXISTS ComplicationTicket (
    ticket_id STRING,
    target_entity_id STRING,
    gap_type STRING,
    hypothesis_query STRING,
    Generated_dorks STRING[],
    status STRING,
    created_at TIMESTAMP,
    PRIMARY KEY (ticket_id)
);

-- Claim Subject/Object Links
CREATE NODE TABLE IF NOT EXISTS AgentTask (
    task_id STRING,
    task_type STRING,
    status STRING,
    params STRING,
    created_at TIMESTAMP,
    PRIMARY KEY (task_id)
);

-- Lande Directed Natural Term Hierarchy
CREATE REL TABLE IF NOT EXISTS TERM_DOMINATES (
    FROM DomainTerm TO DomainTerm,
    visibility_weight DOUBLE,
    directional_asymmetry DOUBLE
);
"""

CREATE_EDGE_TABLES = """
-- Typed Domain Relationships between Entities
CREATE REL TABLE IF NOT EXISTS RELATES_TO (
    FROM Entity TO Entity,
    relation_type STRING,
    weight DOUBLE,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    claim_id STRING,
    is_disputed BOOLEAN
);

-- Verbatim Provenance Grounding (Claim -> SourceDoc)
CREATE REL TABLE IF NOT EXISTS EVIDENCED_BY (
    FROM Claim TO SourceDoc,
    exact_quote STRING,
    start_char INT64,
    end_char INT64,
    nli_score DOUBLE,
    extracted_by_swarm_run STRING
);

-- Claim Subject/Object Links
CREATE REL TABLE IF NOT EXISTS ASSERTS_ABOUT (
    FROM Claim TO Entity,
    role STRING
);

-- Contradiction Edge between Conflicting Claims
CREATE REL TABLE IF NOT EXISTS CONTRADICTS (
    FROM Claim TO Claim,
    contradiction_type STRING,
    severity DOUBLE,
    detected_at TIMESTAMP,
    resolution_notes STRING
);

-- Media Reprint / Information Cascade Tracking
CREATE REL TABLE IF NOT EXISTS REPRINTS_FROM (
    FROM SourceDoc TO SourceDoc,
    similarity_score DOUBLE,
    lag_seconds INT64
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS source_doc_sha256 ON SourceDoc(sha256);
CREATE INDEX IF NOT EXISTS entity_id ON Entity(id);
CREATE INDEX IF NOT EXISTS entity_canonical_name ON Entity(canonical_name);
CREATE INDEX IF NOT EXISTS entity_category ON Entity(category);
CREATE INDEX IF NOT EXISTS claim_id ON Claim(claim_id);
CREATE INDEX IF NOT EXISTS claim_statement ON Claim(statement);
CREATE INDEX IF NOT EXISTS domain_term ON DomainTerm(term);

-- Vector indexes (if available in KùzuDB)
CREATE INDEX IF NOT EXISTS entity_embedding_vector ON Entity(embedding) USING HNSW {
  distance_metric='cosine',
  dimension=1024
};

CREATE INDEX IF NOT EXISTS claim_embedding_vector ON Claim(embedding) USING HNSW {
  distance_metric='cosine',
  dimension=1024
};
"""

IDEMPOTENT_SCRIPT = f"{CREATE_NODE_TABLES}\n{CREATE_EDGE_TABLES}\n{CREATE_INDEXES}"


async def init_kuzu_schema(db_path: str) -> None:
    """Executes DDL + indexes idempotently.
    Can be run on cold start, schema updates, or migration.
    """
    if not os.path.exists(db_path):
        logger.info("Initializing fresh KùzuDB at %s", db_path)
        # First connection will execute script
        return

    logger.info("Ensuring KùzuDB schema at %s", db_path)
    conn = KuzuDB.get_instance(db_path)
    try:
        await conn.cypher_query(IDEMPOTENT_SCRIPT, None)
        logger.info("Schema ensured successfully")
    except Exception as exc:
        logger.error("Schema initialization failed: %s", exc)
        raise


async def ensure_schema(db_path: str) -> None:
    """Helper to be called during startup."""
    await init_kuzu_schema(db_path)
