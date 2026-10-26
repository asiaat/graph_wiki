"""Lande InfoStream: MinHash shingle deduplication & reprint cascade tracking."""

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def minhash_signature(text: str, n: int = 3, num_perm: int = 128) -> list[int]:
    """Generate MinHash signature for text deduplication."""
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
    if not sig1 or not sig2:
        return 0.0
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


def detect_reprint(
    current_doc_text: str,
    existing_docs: list[dict[str, Any]],
    threshold: float = 0.85,
) -> tuple[bool, Optional[str], Optional[float]]:
    """Detect if current document is a reprint of an existing source.
    Returns (is_reprint, source_sha256, similarity_score).
    """
    current_sig = minhash_signature(current_doc_text)
    best_score = 0.0
    best_sha = None

    for doc in existing_docs:
        existing_text = doc.get("content", "")
        existing_sig = minhash_signature(existing_text)
        score = jaccard_similarity(current_sig, existing_sig)
        if score > best_score:
            best_score = score
            best_sha = doc.get("sha256")

    if best_score >= threshold:
        return True, best_sha, best_score
    return False, None, None


def compute_influence_delay(
    source_published_at: str,
    reprint_published_at: str,
) -> int:
    """Compute lag_seconds between source and reprint for influence mapping."""
    from datetime import datetime

    try:
        source_dt = datetime.fromisoformat(source_published_at)
        reprint_dt = datetime.fromisoformat(reprint_published_at)
        delay = (reprint_dt - source_dt).total_seconds()
        return max(0, int(delay))
    except (ValueError, AttributeError):
        return 0
