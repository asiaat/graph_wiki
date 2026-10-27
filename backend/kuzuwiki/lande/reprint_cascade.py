"""Lande InfoStream: MinHash shingle deduplication & reprint cascade tracking.

The reprint detector is the mechanism behind two AGENTS.md rules:

* a reprint must **not** increment the independent corroboration count, and
* a reprint must create a ``[:REPRINTS_FROM {delay_minutes}]`` edge so the
  influence network can be reconstructed.

Both depend on comparing *document content*. Callers therefore have to hand
over the text of the candidate documents - the archived raw text is read back
from the immutable raw vault for exactly this purpose.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def minhash_signature(text: str, n: int = 3, num_perm: int = 128) -> list[int]:
    """Generate MinHash signature for text deduplication."""
    if not text:
        return [0] * num_perm
    shingles = {text[i : i + n] for i in range(len(text) - n + 1)}
    if not shingles:
        return [0] * num_perm

    signatures = []
    for i in range(num_perm):
        min_hash = min(int(hashlib.sha256(f"{i}:{s}".encode()).hexdigest(), 16) for s in shingles)
        signatures.append(min_hash)
    return signatures


def jaccard_similarity(sig1: list[int], sig2: list[int]) -> float:
    """Estimate Jaccard similarity from MinHash signatures."""
    if not sig1 or not sig2 or len(sig1) != len(sig2):
        return 0.0
    matches = sum(1 for a, b in zip(sig1, sig2, strict=False) if a == b)
    return matches / len(sig1)


def detect_reprint(
    current_doc_text: str,
    existing_docs: list[dict[str, Any]],
    threshold: float = 0.85,
    archive_root: Path | str | None = None,
) -> tuple[bool, str | None, float]:
    """Detect if the current document is a reprint of an existing source.

    ``existing_docs`` entries may carry their text inline under ``content``
    or point at an archived copy via ``archive_path`` (resolved against
    ``archive_root``). Returns ``(is_reprint, source_sha256, similarity)``;
    the similarity is always a float so callers can store it unconditionally.
    """
    if not current_doc_text:
        return False, None, 0.0

    current_sig = minhash_signature(current_doc_text)
    best_score = 0.0
    best_sha: str | None = None

    root = Path(archive_root) if archive_root else None

    for doc in existing_docs:
        existing_text = doc.get("content")
        if not existing_text:
            archive_path = doc.get("archive_path")
            if archive_path and root:
                candidate = Path(archive_path)
                if not candidate.is_absolute():
                    candidate = root / candidate.name
                if candidate.exists():
                    try:
                        existing_text = candidate.read_text(encoding="utf-8")
                    except OSError:
                        existing_text = None
        if not existing_text:
            continue

        score = jaccard_similarity(current_sig, minhash_signature(existing_text))
        if score > best_score:
            best_score = score
            best_sha = doc.get("sha256")

    if best_sha and best_score >= threshold:
        return True, best_sha, best_score
    return False, None, best_score


def compute_influence_delay(
    source_published_at: datetime | str | None,
    reprint_published_at: datetime | str | None,
) -> int:
    """Lag in seconds between the original publication and its reprint.

    Returns ``0`` when either timestamp is missing or unparseable - we must
    not invent a cascade delay we cannot support.
    """
    source_dt = _as_datetime(source_published_at)
    reprint_dt = _as_datetime(reprint_published_at)
    if source_dt is None or reprint_dt is None:
        return 0
    delay = (reprint_dt - source_dt).total_seconds()
    return max(0, int(delay))


def _as_datetime(value: datetime | str | None) -> datetime | None:
    """Parse a timestamp into a timezone-aware datetime (UTC assumed if naive)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
