"""Vector embedding client for entities and Wiki pages.

Uses BGE-M3 (or a local fallback) to generate dense embeddings that power
the vector search path in entity resolution and the hybrid GraphRAG query.

The embedding pipeline is optional - if the model is not available or
disabled, the system falls back to Jaro-Winkler alias matching.
"""

from __future__ import annotations

import hashlib
import logging
from typing import List

from kuzuwiki.config import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Thin adapter over a local or remote embedding model."""

    def __init__(self, model_name: str | None = None, dim: int = 1024):
        self.model_name = model_name or settings.jev_embedding_model
        self.dim = dim
        self._encoder = None

    def _get_encoder(self):
        """Lazily load the encoder only when needed."""
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._encoder = SentenceTransformer(self.model_name)
                logger.info("Loaded embedding model: %s", self.model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed; vector path disabled")
                return None
            except Exception as exc:
                logger.warning("Failed to load embedding model %s: %s", self.model_name, exc)
                return None
        return self._encoder

    def embed_texts(self, texts: List[str]) -> List[List[float]] | None:
        """Generate embeddings for a list of texts."""
        encoder = self._get_encoder()
        if encoder is None:
            return None
        try:
            embeddings = encoder.encode(texts, normalize_embeddings=True)
            return [emb.tolist() if hasattr(emb, "tolist") else list(emb) for emb in embeddings]
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            return None

    def embed_text(self, text: str) -> List[float] | None:
        """Generate embedding for a single text."""
        result = self.embed_texts([text])
        return result[0] if result else None


class EmbeddingCache:
    """Simple in-memory cache for embeddings, keyed by content hash."""

    def __init__(self):
        self._cache: dict[str, List[float]] = {}

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def get(self, text: str) -> List[float] | None:
        return self._cache.get(self._hash(text))

    def set(self, text: str, embedding: List[float]) -> None:
        self._cache[self._hash(text)] = embedding


# Global singleton
_embedding_client: EmbeddingClient | None = None
_embedding_cache: EmbeddingCache | None = None


def get_embedding_client() -> EmbeddingClient | None:
    """Get or create the global embedding client."""
    global _embedding_client
    if _embedding_client is None:
        if settings.jev_embedding_model:
            _embedding_client = EmbeddingClient()
    return _embedding_client


def get_embedding_cache() -> EmbeddingCache:
    """Get or create the global embedding cache."""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache


def embed_entity_summary(name: str, summary: str, category: str) -> List[float] | None:
    """Generate an embedding for an entity from its canonical name, summary, and category."""
    client = get_embedding_client()
    if client is None:
        return None
    text = f"{name} {summary} {category}".strip()
    cache = get_embedding_cache()
    cached = cache.get(text)
    if cached is not None:
        return cached
    embedding = client.embed_text(text)
    if embedding is not None:
        cache.set(text, embedding)
    return embedding
