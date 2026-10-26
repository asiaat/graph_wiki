"""Agent 1: GatekeeperSlopAgent — Pre-Ingest Filter & Admiralty Classifier.
Protects the knowledge base from AI slop, SEO spam, circular reporting, and unverified propaganda.
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.config import settings
from app.db.kuzu_client import KuzuClient
from app.db.wiki_sync import WikiSync
from app.jev.schemas import (
    RawDocumentPayload,
    JEVAttackIndexMetrics,
    JEVDistillationBundle,
    AdmiraltyReliability,
    EntityCategory,
    RelationType,
    VerbatimSpan,
)
from app.jev.slop_classifier import classify_slop, should_quarantine_slop
from app.lande.hvg_network import compute_hvg
from app.lande.reprint_cascade import detect_reprint

logger = logging.getLogger(__name__)


class GatekeeperResult(BaseModel):
    accepted: bool
    quarantined: bool
    slop_score: float
    admiralty: AdmiraltyReliability
    credibility_rank: int
    quarantine_reason: Optional[str] = None
    doc_sha256: str
    hub_terms: list[str]


class GatekeeperSlopAgent:
    def __init__(
        self,
        kuzu: KuzuClient,
        raw_vault_path: str = "/data/raw_vault",
        wiki_vault_path: str = "/data/wiki",
    ):
        self.kuzu = kuzu
        self.raw_vault = Path(raw_vault_path)
        self.raw_vault.mkdir(parents=True, exist_ok=True)
        self.wiki_sync = WikiSync(kuzu, wiki_vault_path)

    async def ingest_document(self, payload: RawDocumentPayload) -> GatekeeperResult:
        """Full gatekeeping pipeline for a raw document."""
        content = payload.content or ""
        if not content:
            return GatekeeperResult(
                accepted=False,
                quarantined=True,
                slop_score=1.0,
                admiralty=AdmiraltyReliability.F,
                credibility_rank=6,
                quarantine_reason="Empty document",
                doc_sha256="",
                hub_terms=[],
            )

        # SHA-256 hash for immutable archival
        doc_sha256 = hashlib.sha256(content.encode()).hexdigest()

        # Archive raw document immutably
        archive_path = self.raw_vault / f"{doc_sha256}.txt"
        if not archive_path.exists():
            archive_path.write_text(content, encoding="utf-8")
            logger.info("Archived raw document: %s", archive_path)

        # Slop classification
        slop_result = classify_slop(content, str(payload.domain or ""))
        slop_score = slop_result.slop_probability

        # Admiralty code assignment (heuristic: default C for unknown)
        admiralty = AdmiraltyReliability.C
        credibility_rank = 3

        # Quarantine check
        quarantined = should_quarantine_slop(slop_score, str(payload.domain or ""))

        # Lande HVG computation for hub terms
        hvg_result = compute_hvg(content)
        hub_terms = hvg_result.hub_terms

        # Reprint detection against existing SourceDocs
        existing_docs = await self.kuzu.read(
            "MATCH (s:SourceDoc) RETURN s.sha256, s.title, s.domain, s.published_at"
        )

        is_reprint, reprint_sha, similarity = detect_reprint(
            content,
            [
                {"sha256": r[0], "title": r[1], "domain": r[2], "published_at": str(r[3])}
                for r in existing_docs
            ],
        )

        if is_reprint:
            logger.info("Detected reprint of %s (similarity: %.2f)", reprint_sha, similarity)

        # SourceDoc node creation
        ingested_at = datetime.utcnow().isoformat() + "Z"
        cypher = """
        MERGE (s:SourceDoc {sha256: $sha256})
        ON CREATE SET
            s.uri = $uri,
            s.title = $title,
            s.domain = $domain,
            s.published_at = $published_at,
            s.ingested_at = $ingested_at,
            s.admiralty_reliability = $admiralty,
            s.credibility_rank = $credibility_rank,
            s.slop_score = $slop_score,
            s.attack_index = $slop_score,
            s.raw_archive_path = $archive_path
        """
        params = {
            "sha256": doc_sha256,
            "uri": payload.uri or "",
            "title": payload.title or "",
            "domain": str(payload.domain or ""),
            "published_at": payload.published_at or "",
            "ingested_at": ingested_at,
            "admiralty": str(admiralty),
            "credibility_rank": credibility_rank,
            "slop_score": slop_score,
            "archive_path": str(archive_path),
        }
        await self.kuzu.enqueue_write(cypher, params)

        accepted = not quarantined

        return GatekeeperResult(
            accepted=accepted,
            quarantined=quarantined,
            slop_score=slop_score,
            admiralty=admiralty,
            credibility_rank=credibility_rank,
            quarantine_reason=f"Slop score {slop_score:.2f} > 0.65" if quarantined else None,
            doc_sha256=doc_sha256,
            hub_terms=hub_terms,
        )
