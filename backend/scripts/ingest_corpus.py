#!/usr/bin/env python3
"""P3: OSINT Corpus Ingestion through the Compile Pipeline

Phase 3 of the KuzuWiki-OSINT ingest pipeline:

This script walks the corpus root directory (`/root/proj/osint_berlin26`), finds
all source documents (markdown files, summaries, etc.), runs them through the
Gatekeeper → Swarm → Compiler pipeline, and compiles the extracted knowledge
claims into the KùzuDB graph and wiki vault.

The pipeline ensures:
- Slop filtering and Admiralty classification (Agent 1: Gatekeeper)
- Deterministic claim extraction via Virtual Expert Swarm (Agent 3)
- Verbatim provenance and structured claims (Agent 4: Compiler)
- Human-readable wiki dossiers and semantic consistency (Agent 4)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kuzuwiki.api.routes_ingest import RawDocumentPayload
from kuzuwiki.agents.orchestrator import Orchestrator
from kuzuwiki.config import settings
from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.schema_init import ensure_schema
from kuzuwiki.db.wiki_sync import WikiSync
from kuzuwiki.jev.schemas import SourceType, Sensitivity

logger = logging.getLogger("p3_corpus_ingestion")

# --------------------------------------------------------------------------
# Corpus Discovery
# --------------------------------------------------------------------------

MAX_FILES = 10_000  # Safety limit for large corpora


def _discover_documents(corpus_root: Path) -> list[tuple[Path, str]]:
    """Walk the corpus root and return a list of (file_path, document_type).

    Discovers documents from:
    1. ``summary.md`` files in report directories
    2. ``.md`` files at the corpus root (they are already documents)
    3. ``*.md`` files found by glob search (for completeness)
    """
    documents: list[tuple[Path, str]] = []

    # 1. From report directories: summary.md
    for summary in corpus_root.rglob("reports/*/summary.md"):
        documents.append((summary, "summary"))

    # 2. From corpus root: .md files (these ARE the documents themselves)
    for md in corpus_root.glob("*.md"):
        if md.name in ("README.md", "CONTRIBUTING.md"):
            continue
        documents.append((md, "document"))

    # 3. Any other .md files in the corpus (excluding reports/*/ summaries which already captured)
    for md in corpus_root.rglob("*.md"):
        # Skip already discovered files
        if md in [p for p, _ in documents]:
            continue
        # Skip report dir summaries and __pycache__ etc.
        if "/reports/" in str(md) or "/__pycache__/" in str(md):
            continue
        documents.append((md, "document"))

    logger.info(
        "Discovered %d source document(s) in corpus root '%s'",
        len(documents),
        corpus_root.absolute(),
    )
    return documents[:MAX_FILES]


def _load_metadata(summary_path: Path | None) -> dict[str, Any] | None:
    """Try to load metadata.json from the same directory as the document."""
    if not summary_path:
        return None

    metadata_path = summary_path.parent / "metadata.json"
    if metadata_path.exists():
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _create_payload(doc_path: Path, doc_type: str, corpus_root: Path) -> RawDocumentPayload | None:
    """Create a RawDocumentPayload from a source document file."""
    try:
        content = doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read %s: %s", doc_path, exc)
        return None

    if not content or not content.strip():
        logger.warning("Empty content in %s", doc_path)
        return None

    # Extract basic metadata
    title = doc_path.name.replace(".md", "").replace(".pdf", "")
    domain = "osint_berlin26.local"

    # Load metadata if available
    metadata = _load_metadata(doc_path if doc_type == "summary" else None)

    # Create a stable URI
    uri = f"{doc_path.relative_to(corpus_root).as_posix()}"

    # Build payload
    payload = RawDocumentPayload(
        content=content,
        uri=uri,
        title=title,
        domain=domain,
        published_at=metadata.get("created_date") if metadata else None,
        domain_mode="OSINT_BERLIN26_CORPUS",
        analysis_domain="osint_berlin26",
        source_type=SourceType.ANALYST_REPORT,
        sensitivity=Sensitivity.PUBLIC,
    )
    return payload


# --------------------------------------------------------------------------
# Ingestion Orchestration
# --------------------------------------------------------------------------


async def run_p3_ingestion(
    corpus_root: str = "/root/proj/osint_berlin26",
    db_path: str = "/data/kuzudb/graph.kuzu",
    wiki_vault_path: str = "/data/wiki",
    max_docs: int | None = None,
) -> dict[str, Any]:
    """Run the P3 compile pipeline on the entire corpus."""
    corpus_root = Path(corpus_root)
    if not corpus_root.exists() or not corpus_root.is_dir():
        raise ValueError(f"Corpus root not found: {corpus_root}")

    logger.info(
        "Starting P3 corpus ingestion for %s",
        corpus_root.absolute(),
    )

    # Initialize KùzuDB
    client = await KuzuClient.init(db_path)
    try:
        await ensure_schema(client)

        # Initialize orchestrator with the configured SwarmExtractor
        orchestrator = Orchestrator(
            client,
            wiki_vault_path=wiki_vault_path,
            raw_vault_path="/data/raw_vault",
            quarantine_path="/data/quarantine",
        )

        # Discover documents
        documents = _discover_documents(corpus_root)
        if max_docs:
            documents = documents[:max_docs]

        # Process each document
        stats = {
            "total_docs": len(documents),
            "accepted": 0,
            "quarantined": 0,
            "compile_counts": {"entities": 0, "relations": 0, "claims": 0},
            "errors": [],
        }

        for i, (doc_path, doc_type) in enumerate(documents, 1):
            logger.info(
                "[%d/%d] Processing %s (%s)",
                i,
                len(documents),
                doc_path.relative_to(corpus_root),
                doc_type,
            )

            try:
                payload = _create_payload(doc_path, doc_type, corpus_root)
                if not payload:
                    stats["errors"].append(f"{doc_path}: Failed to create payload")
                    continue

                state = await orchestrator.ingest_and_compile(payload)

                if state.get("error"):
                    logger.warning(
                        "Document %s error: %s",
                        doc_path.name,
                        state["error"],
                    )
                    stats["errors"].append(f"{doc_path}: {state['error']}")
                    continue

                gatekeeper_result = state.get("gatekeeper_result")
                if not gatekeeper_result:
                    stats["errors"].append(f"{doc_path}: No gatekeeper result")
                    continue

                accepted = bool(getattr(gatekeeper_result, "accepted", False))
                quarantined = bool(getattr(gatekeeper_result, "quarantined", False))

                if accepted:
                    stats["accepted"] += 1
                    compile_stats = state.get("compile_stats", {})
                    stats["compile_counts"]["entities"] += compile_stats.get("entities", 0)
                    stats["compile_counts"]["relations"] += compile_stats.get("relations", 0)
                    stats["compile_counts"]["claims"] += compile_stats.get("claims", 0)
                elif quarantined:
                    stats["quarantined"] += 1
                else:
                    logger.warning(
                        "Document %s result: accepted=%s, quarantined=%s",
                        doc_path.name,
                        accepted,
                        quarantined,
                    )

            except Exception as exc:
                logger.error(
                    "Failed to process document %s: %s",
                    doc_path,
                    exc,
                    exc_info=True,
                )
                stats["errors"].append(f"{doc_path}: {exc}")

        logger.info("P3 corpus ingestion complete: %s", stats)
        return stats

    finally:
        await client.close()
        KuzuClient._shared_instance = None


# --------------------------------------------------------------------------
# Main Entry Point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 3: Ingest OSINT corpus through the compile pipeline."
    )
    parser.add_argument(
        "--corpus",
        default="/root/proj/osint_berlin26",
        help="Path to the OSINT corpus root directory",
    )
    parser.add_argument(
        "--db",
        default="/data/kuzudb/graph.kuzu",
        help="Path to KùzuDB file",
    )
    parser.add_argument(
        "--wiki",
        default="/data/wiki",
        help="Path to the wiki vault",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        help="Maximum number of documents to process (for testing)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(
        run_p3_ingestion(
            corpus_root=args.corpus,
            db_path=args.db,
            wiki_vault_path=args.wiki,
            max_docs=args.max_docs,
        )
    )
