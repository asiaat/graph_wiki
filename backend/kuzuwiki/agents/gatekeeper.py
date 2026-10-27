"""Agent 1: GatekeeperSlopAgent — pre-ingest filter & Admiralty classifier.

Protects the knowledge base from AI slop, SEO spam, circular reporting and
unverified propaganda *before* anything reaches the compiled graph.

Order of operations:

1. Content-addressed archival of the raw document (immutable, never rewritten).
2. Deterministic slop scoring (prose statistics only).
3. Admiralty classification of the source.
4. Quarantine decision - quarantined documents are archived and recorded, but
   they never enter the compiled graph.
5. Lande HVG hub-term extraction for the downstream swarm.
6. Reprint detection against previously ingested documents.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from kuzuwiki.db.kuzu_client import KuzuClient
from kuzuwiki.db.wiki_sync import WikiSync
from kuzuwiki.jev.admiralty import classify_source
from kuzuwiki.jev.schemas import (
    AdmiraltyReliability,
    JEVAttackIndexMetrics,
    RawDocumentPayload,
)
from kuzuwiki.jev.slop_classifier import (
    classify_slop,
    metrics_to_attack_index,
    should_quarantine_slop,
)
from kuzuwiki.lande.hvg_network import compute_hvg
from kuzuwiki.lande.reprint_cascade import detect_reprint

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string into an aware datetime, or ``None``."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            logger.debug("Unparseable timestamp: %r", value)
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class GatekeeperResult(BaseModel):
    accepted: bool
    quarantined: bool
    slop_score: float
    admiralty: AdmiraltyReliability
    credibility_rank: int
    quarantine_reason: str | None = None
    doc_sha256: str
    hub_terms: list[str]
    #: Attack-Index vector - carried into the JEV bundle. This field is what
    #: the orchestrator hands to the swarm extractor.
    slop_metrics: JEVAttackIndexMetrics | None = None
    is_reprint: bool = False
    reprint_of: str | None = None
    similarity: float = 0.0
    archive_path: str | None = None


class GatekeeperSlopAgent:
    def __init__(
        self,
        kuzu: KuzuClient,
        raw_vault_path: str = "/data/raw_vault",
        wiki_vault_path: str = "/data/wiki",
        quarantine_path: str | None = None,
    ):
        self.kuzu = kuzu
        self.raw_vault = Path(raw_vault_path)
        self.raw_vault.mkdir(parents=True, exist_ok=True)
        self.quarantine_vault = Path(quarantine_path) if quarantine_path else None
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
                slop_metrics=metrics_to_attack_index(classify_slop(""), AdmiraltyReliability.F, 6),
            )

        # 1. Content-addressed archival (immutable: never rewritten).
        doc_sha256 = hashlib.sha256(content.encode()).hexdigest()
        archive_path = self.raw_vault / f"{doc_sha256}.txt"
        if not archive_path.exists():
            archive_path.write_text(content, encoding="utf-8")
            logger.info("Archived raw document: %s", archive_path)

        # 2. Slop classification (prose statistics only).
        slop_result = classify_slop(content)
        slop_score = slop_result.slop_probability

        # 3. Admiralty classification of the source.
        corroborations = await self._count_corroborations(payload.domain)
        assessment = classify_source(content, payload.domain, corroborations)
        admiralty = assessment.reliability
        credibility_rank = assessment.credibility_rank

        slop_metrics = metrics_to_attack_index(slop_result, admiralty, credibility_rank)

        # 4. Quarantine decision.
        domain_mode = getattr(payload, "domain_mode", "") or ""
        quarantined = should_quarantine_slop(slop_score, domain_mode)
        quarantine_reason = f"Slop score {slop_score:.2f} > 0.65" if quarantined else None

        # 5. Lande HVG hub terms.
        hvg_result = compute_hvg(content)
        hub_terms = hvg_result.hub_terms

        # 6. Reprint detection - the *content* must be supplied, otherwise every
        #    candidate hashes as empty and nothing is ever detected.
        existing_docs = await self.kuzu.read(
            "MATCH (s:SourceDoc) WHERE NOT s.is_quarantined "
            "RETURN s.sha256 AS sha256, s.uri AS uri, s.domain AS domain, "
            "s.published_at AS published_at, s.raw_archive_path AS archive_path"
        )
        candidates = []
        for row in existing_docs:
            candidates.append(
                {
                    "sha256": row.get("sha256"),
                    "uri": row.get("uri"),
                    "domain": row.get("domain"),
                    "published_at": row.get("published_at"),
                    "archive_path": row.get("archive_path"),
                }
            )

        is_reprint, reprint_sha, similarity = detect_reprint(
            content,
            candidates,
            archive_root=self.raw_vault,
        )
        if is_reprint:
            logger.info("Detected reprint of %s (similarity: %.2f)", reprint_sha, similarity)

        # Record the SourceDoc. Quarantined documents are recorded *as
        # quarantined* so they can be audited, but they never become part of
        # the compiled graph.
        if quarantined and self.quarantine_vault is not None:
            self.quarantine_vault.mkdir(parents=True, exist_ok=True)
            qpath = self.quarantine_vault / f"{doc_sha256}.txt"
            if not qpath.exists():
                qpath.write_text(content, encoding="utf-8")
            logger.warning("Document quarantined as slop: %s", qpath)

        await self.kuzu.write(
            """
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
                s.attack_index = $attack_index,
                s.raw_archive_path = $archive_path,
                s.primary_term = $primary_term,
                s.is_quarantined = $is_quarantined,
                s.quarantined_reason = $quarantine_reason
            """,
            {
                "sha256": doc_sha256,
                "uri": payload.uri or "",
                "title": payload.title or "",
                "domain": str(payload.domain or ""),
                "published_at": _parse_timestamp(payload.published_at),
                "ingested_at": _utcnow(),
                "admiralty": admiralty.value,
                "credibility_rank": credibility_rank,
                "slop_score": slop_score,
                "attack_index": slop_metrics.emotional_intensity,
                "archive_path": str(archive_path),
                "primary_term": hub_terms[0] if hub_terms else "",
                "is_quarantined": quarantined,
                "quarantine_reason": quarantine_reason,
            },
        )

        if is_reprint and reprint_sha:
            await self._write_reprint_edge(
                doc_sha256, reprint_sha, similarity, payload.published_at
            )

        return GatekeeperResult(
            accepted=not quarantined,
            quarantined=quarantined,
            slop_score=slop_score,
            admiralty=admiralty,
            credibility_rank=credibility_rank,
            quarantine_reason=quarantine_reason,
            doc_sha256=doc_sha256,
            hub_terms=hub_terms,
            slop_metrics=slop_metrics,
            is_reprint=is_reprint,
            reprint_of=reprint_sha,
            similarity=similarity,
            archive_path=str(archive_path),
        )

    async def _count_corroborations(self, domain: str | None) -> int:
        """How many already-ingested documents share this source domain."""
        if not domain:
            return 0
        rows = await self.kuzu.read(
            "MATCH (s:SourceDoc) WHERE s.domain = $domain AND NOT s.is_quarantined "
            "RETURN count(s) AS n",
            {"domain": str(domain)},
        )
        return int(rows[0]["n"]) if rows else 0

    async def _write_reprint_edge(
        self, doc_sha256: str, reprint_sha: str, similarity: float, published_at: str | None
    ) -> None:
        """Record the information cascade: this document reprints ``reprint_sha``."""
        from kuzuwiki.lande.reprint_cascade import compute_influence_delay

        rows = await self.kuzu.read(
            "MATCH (s:SourceDoc {sha256: $sha}) RETURN s.published_at AS published_at",
            {"sha": reprint_sha},
        )
        original_time = rows[0]["published_at"] if rows else None
        delay = compute_influence_delay(original_time, _parse_timestamp(published_at))
        try:
            await self.kuzu.write(
                """
                MATCH (a:SourceDoc {sha256: $reprint}), (b:SourceDoc {sha256: $original})
                MERGE (a)-[r:REPRINTS_FROM]->(b)
                SET r.similarity_score = $similarity, r.lag_seconds = $lag
                """,
                {
                    "reprint": doc_sha256,
                    "original": reprint_sha,
                    "similarity": similarity,
                    "lag": delay,
                },
            )
        except Exception as exc:
            logger.warning("Could not record REPRINTS_FROM edge: %s", exc)
