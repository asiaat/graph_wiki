"""DeBERTa NLI verifier + deterministic verbatim substring gate."""

import logging
from typing import Optional

from pydantic import BaseModel

from app.jev.schemas import JEVExtractedRelation, VerbatimSpan

logger = logging.getLogger(__name__)


class NLIResult(BaseModel):
    relation: JEVExtractedRelation
    entailment_score: float
    is_entailed: bool
    quote_verified: bool
    pass_or_fail: bool


class NLIEntity(BaseModel):
    entity_name: str
    start_char: int
    end_char: int


class NLIEntityOutput(BaseModel):
    entities: list[NLIEntity]


def verify_quotebound(
    relation: JEVExtractedRelation,
    raw_document_text: str,
    strict: bool = True,
) -> NLIResult:
    """Verbatim Citation Gate: assert quote in raw_document_text.
    If strict=True, also requires NLI entailment >= 0.85.
    """
    quote = relation.evidence.exact_quote
    start = relation.evidence.start_char
    end = relation.evidence.end_char

    # Deterministic substring alignment check
    quote_in_text = quote in raw_document_text
    span_match = (
        raw_document_text[start:end] == quote if start < end <= len(raw_document_text) else False
    )

    quote_verified = quote_in_text and span_match

    # NLI entailment check (placeholder: cross-encoder would go here)
    # For now, compute a simple heuristic: overlap ratio between quote and relation statement
    quote_tokens = set(quote.lower().split())
    statement_tokens = set(relation.source_entity.split() + relation.target_entity.split())
    overlap = len(quote_tokens & statement_tokens) / max(len(quote_tokens), 1)

    entailment_score = min(1.0, overlap * 1.2)
    is_entailed = entailment_score >= 0.85

    pass_or_fail = quote_verified and (is_entailed or not strict)

    return NLIResult(
        relation=relation,
        entailment_score=entailment_score,
        is_entailed=is_entailed,
        quote_verified=quote_verified,
        pass_or_fail=pass_or_fail,
    )


class NLIClient:
    """Cross-encoder NLI client (DeBERTa). Stubs the real model load."""

    def __init__(
        self, model_name: str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    ):
        self.model_name = model_name
        self._model_loaded = False
        logger.info("NLI client initialized (deferred model load): %s", model_name)

    def verify_batch(
        self,
        relations: list[JEVExtractedRelation],
        raw_document_text: str,
    ) -> list[NLIResult]:
        return [verify_quotebound(r, raw_document_text, strict=True) for r in relations]

    def verify_single(
        self,
        relation: JEVExtractedRelation,
        raw_document_text: str,
    ) -> NLIResult:
        return verify_quotebound(relation, raw_document_text, strict=True)
