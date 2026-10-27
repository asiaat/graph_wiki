"""Verbatim grounding + entailment verification (the zero-hallucination gate).

The gate has two independent halves:

**Quote grounding.** The exact quote must be a literal substring of the raw
archived document. LLM-supplied character offsets are *not* trusted; the
offsets are re-derived from the document via ``str.find``. A relation whose
quote cannot be located is rejected outright.

**Entailment.** The extracted triple must actually be supported by the quote.
The default backend is a deterministic lexical entailment scorer: the quote
must name both entities, must contain a lexical trigger for the relation type,
and must cover the content of the triple. It is fast, offline, reproducible
and unit-testable - which matters more than raw accuracy for a gate that must
never let an ungrounded claim through.

A cross-encoder backend (DeBERTa) can be plugged in behind the same
:class:`NLIClient` interface without touching the pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from pydantic import BaseModel

from kuzuwiki.jev.schemas import JEVExtractedRelation, RelationType
from kuzuwiki.jev.textutil import content_tokens, stem, stemmed_tokens

logger = logging.getLogger(__name__)

#: Entailment threshold from AGENTS.md / PRD §6.
NLI_THRESHOLD = 0.85

#: Lexical triggers per relation type. A quote must contain at least one.
RELATION_TRIGGERS: dict[RelationType, tuple[str, ...]] = {
    RelationType.OWNS_CONTROLS: (
        "own",
        "owns",
        "owned",
        "control",
        "controls",
        "controlled",
        "subsidiary",
        "parent",
        "majority",
        "stake",
        "holding",
        "holds",
        "shares",
    ),
    RelationType.SUPPLIES_COMPONENT: (
        "supply",
        "supplies",
        "supplied",
        "supplier",
        "vendor",
        "provide",
        "provides",
        "provided",
        "deliver",
        "delivers",
        "delivered",
        "ship",
        "ships",
    ),
    RelationType.MANUFACTURES: (
        "manufacture",
        "manufactures",
        "manufactured",
        "manufacturing",
        "maker",
        "make",
        "makes",
        "made",
        "produce",
        "produces",
        "produced",
        "builder",
        "built",
        "assembles",
    ),
    RelationType.FUNDS: (
        "fund",
        "funds",
        "funded",
        "funding",
        "finance",
        "finances",
        "financed",
        "invest",
        "invests",
        "invested",
        "grant",
        "grants",
        "granted",
        "paid",
        "pays",
        "sponsored",
        "sponsors",
    ),
    RelationType.AFFILIATED_WITH: (
        "affiliate",
        "affiliated",
        "partnership",
        "partner",
        "member",
        "alliance",
        "allied",
        "linked",
        "association",
        "associated",
        "associated with",
    ),
    RelationType.AMPLIFIES_NARRATIVE: (
        "amplify",
        "amplifies",
        "amplified",
        "promote",
        "promotes",
        "promoted",
        "spread",
        "spreads",
        "published",
        "publishes",
        "broadcast",
        "broadcasts",
        "aired",
        "carried",
        "amplifying",
    ),
    RelationType.CONTRADICTS_CLAIM: (
        "contradict",
        "contradicts",
        "contradicted",
        "dispute",
        "disputed",
        "denies",
        "denied",
        "refutes",
        "refuted",
        "contrary",
        "disputes",
    ),
    RelationType.PARTICIPATED_IN: (
        "participated",
        "participates",
        "participation",
        "attended",
        "attend",
        "joined",
        "involved",
        "speaker",
        "delegation",
    ),
    RelationType.SANCTIONED_UNDER: (
        "sanction",
        "sanctions",
        "sanctioned",
        "designated",
        "designation",
        "blacklist",
        "blacklisted",
        "embargo",
        "embargoed",
        "restricted",
    ),
    RelationType.HIERARCHY_PARENT_OF: (
        "part of",
        "subclass",
        "category",
        "type of",
        "parent",
        "parent of",
        "contains",
        "component of",
        "belongs to",
        "under",
    ),
}

#: Canonical predicate phrase used when building the triple statement.
RELATION_PREDICATE: dict[RelationType, str] = {
    RelationType.OWNS_CONTROLS: "owns and controls",
    RelationType.SUPPLIES_COMPONENT: "supplies a component",
    RelationType.MANUFACTURES: "manufactures",
    RelationType.FUNDS: "funds",
    RelationType.AFFILIATED_WITH: "is affiliated with",
    RelationType.AMPLIFIES_NARRATIVE: "amplifies a narrative",
    RelationType.CONTRADICTS_CLAIM: "contradicts a claim",
    RelationType.PARTICIPATED_IN: "participated in",
    RelationType.SANCTIONED_UNDER: "is sanctioned under",
    RelationType.HIERARCHY_PARENT_OF: "is a parent of",
}

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


class NLIResult(BaseModel):
    relation: JEVExtractedRelation
    entailment_score: float
    is_entailed: bool
    quote_verified: bool
    pass_or_fail: bool
    reject_reason: str | None = None
    grounded_start: int | None = None
    grounded_end: int | None = None
    entity_coverage: float = 0.0
    predicate_matched: bool = False
    backend: str = "lexical"

    @property
    def threshold(self) -> float:
        return NLI_THRESHOLD


class NLIEntity(BaseModel):
    entity_name: str
    start_char: int
    end_char: int


class NLIEntityOutput(BaseModel):
    entities: list[NLIEntity]


# ---------------------------------------------------------------------------
# Deterministic lexical entailment
# ---------------------------------------------------------------------------


def _entity_coverage(entity_name: str, quote_stems: set[str]) -> float:
    """Fraction of the entity's content tokens that occur in the quote."""
    tokens = content_tokens(entity_name)
    if not tokens:
        return 0.0
    stemmed = {stem(t) for t in tokens}
    hits = sum(1 for t in stemmed if t in quote_stems)
    return hits / len(stemmed)


def _predicate_matched(relation_type: RelationType, quote_text: str) -> bool:
    triggers = RELATION_TRIGGERS.get(relation_type, ())
    lowered = quote_text.lower()
    return any(trigger in lowered for trigger in triggers)


def _statement_tokens(relation: JEVExtractedRelation) -> set[str]:
    predicate = RELATION_PREDICATE.get(relation.relation_type, relation.relation_type.value)
    return stemmed_tokens(f"{relation.source_entity} {predicate} {relation.target_entity}")


def score_entailment(relation: JEVExtractedRelation, quote: str) -> tuple[float, dict[str, Any]]:
    """Score how strongly ``quote`` entails the extracted triple.

    Returns ``(score, details)`` where score is in ``[0, 1]``.
    """
    quote_lower = quote.lower()
    quote_stems = stemmed_tokens(quote)

    src_cov = _entity_coverage(relation.source_entity, quote_stems)
    tgt_cov = _entity_coverage(relation.target_entity, quote_stems)
    entity_cov = min(src_cov, tgt_cov)

    # Both entities must be named by the quote. Without this a quote about an
    # unrelated subject could still score on predicate overlap alone.
    entities_present = src_cov >= 0.5 and tgt_cov >= 0.5
    predicate_ok = _predicate_matched(relation.relation_type, quote)

    statement = _statement_tokens(relation)
    recall = len(statement & quote_stems) / len(statement) if statement else 0.0

    details = {
        "source_coverage": src_cov,
        "target_coverage": tgt_cov,
        "entity_coverage": entity_cov,
        "entities_present": entities_present,
        "predicate_matched": predicate_ok,
        "token_recall": recall,
    }

    if not entities_present:
        # A relation whose quote does not name both parties is not grounded.
        return 0.0, details

    score = 0.40 * entity_cov + 0.20 * (1.0 if predicate_ok else 0.0) + 0.40 * recall

    # Temporal consistency: if the relation carries a validity year, the quote
    # should not assert a *different* year.
    if relation.temporal_valid_from:
        wanted = re.findall(r"\d{4}", relation.temporal_valid_from)
        found = _YEAR_RE.findall(quote_lower)
        if wanted and found and not any(w in found for w in wanted):
            score = max(0.0, score - 0.10)
            details["temporal_conflict"] = True

    return min(1.0, score), details


# ---------------------------------------------------------------------------
# Verbatim grounding
# ---------------------------------------------------------------------------


def locate_quote(quote: str, raw_document_text: str) -> tuple[int, int] | None:
    """Find the quote in the raw text. Returns ``(start, end)`` or ``None``."""
    if not quote:
        return None
    start = raw_document_text.find(quote)
    if start < 0:
        # Tolerate whitespace differences (PDF extraction often reflows text).
        pattern = r"\s+".join(re.escape(tok) for tok in quote.split())
        match = re.search(pattern, raw_document_text)
        if match:
            return match.start(), match.end()
        return None
    return start, start + len(quote)


def verify_quotebound(
    relation: JEVExtractedRelation,
    raw_document_text: str,
    strict: bool = True,
    backend: EntailmentBackend | None = None,
) -> NLIResult:
    """Verbatim Citation Gate: the quote must exist verbatim and entail the triple.

    With ``strict=True`` (the default) the relation is rejected unless the
    entailment score reaches :data:`NLI_THRESHOLD`.
    """
    quote = relation.evidence.exact_quote

    span = locate_quote(quote, raw_document_text)
    quote_verified = span is not None
    grounded_start, grounded_end = span if span else (None, None)

    backend = backend or LexicalEntailmentBackend()

    if not quote_verified:
        return NLIResult(
            relation=relation,
            entailment_score=0.0,
            is_entailed=False,
            quote_verified=False,
            pass_or_fail=False,
            reject_reason="quote_not_found_in_source",
            grounded_start=None,
            grounded_end=None,
            backend=backend.name,
        )

    score, details = backend.score(relation, quote, raw_document_text)
    is_entailed = score >= NLI_THRESHOLD

    reject_reason: str | None = None
    if not details.get("entities_present", False):
        reject_reason = "quote_does_not_name_both_entities"
    elif not is_entailed:
        reject_reason = "entailment_below_threshold"

    return NLIResult(
        relation=relation,
        entailment_score=score,
        is_entailed=is_entailed,
        quote_verified=True,
        pass_or_fail=quote_verified and (is_entailed or not strict),
        reject_reason=reject_reason,
        grounded_start=grounded_start,
        grounded_end=grounded_end,
        entity_coverage=float(details.get("entity_coverage", 0.0)),
        predicate_matched=bool(details.get("predicate_matched", False)),
        backend=backend.name,
    )


# ---------------------------------------------------------------------------
# Pluggable backends
# ---------------------------------------------------------------------------


class EntailmentBackend(Protocol):
    name: str

    def score(
        self, relation: JEVExtractedRelation, quote: str, raw_document_text: str
    ) -> tuple[float, dict[str, Any]]: ...


class LexicalEntailmentBackend:
    """Deterministic lexical entailment (default; offline and reproducible)."""

    name = "lexical"

    def score(
        self, relation: JEVExtractedRelation, quote: str, raw_document_text: str
    ) -> tuple[float, dict[str, Any]]:
        return score_entailment(relation, quote)


class DebertaEntailmentBackend:
    """Cross-encoder entailment backend (optional, requires ``transformers``).

    Kept behind the same interface so the pipeline does not change when the
    heavyweight dependency is installed.
    """

    name = "deberta"

    def __init__(
        self, model_name: str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    ):
        self.model_name = model_name
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            from transformers import pipeline  # noqa: PLC0415 - optional dependency

            self._pipeline = pipeline("text-classification", model=self.model_name)
        return self._pipeline

    def score(
        self, relation: JEVExtractedRelation, quote: str, raw_document_text: str
    ) -> tuple[float, dict[str, Any]]:
        statement = (
            f"{relation.source_entity} "
            f"{RELATION_PREDICATE.get(relation.relation_type, relation.relation_type.value)} "
            f"{relation.target_entity}"
        )
        try:
            classifier = self._load()
            result = classifier(f"{statement}", hypothesis=quote)
            label = str(result[0]["label"]).upper()
            score = float(result[0]["score"]) if "ENTAIL" in label else 0.0
        except Exception as exc:  # pragma: no cover - optional path
            logger.warning("Cross-encoder backend unavailable (%s); using lexical score", exc)
            return score_entailment(relation, quote)
        details = {"predicate_matched": True, "entities_present": True}
        return score, details


class NLIClient:
    """Facade over the configured entailment backend."""

    def __init__(
        self,
        model_name: str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli",
        backend: EntailmentBackend | None = None,
    ):
        self.model_name = model_name
        self.backend: EntailmentBackend = backend or LexicalEntailmentBackend()

    def verify_batch(
        self,
        relations: list[JEVExtractedRelation],
        raw_document_text: str,
        strict: bool = True,
    ) -> list[NLIResult]:
        return [
            verify_quotebound(r, raw_document_text, strict=strict, backend=self.backend)
            for r in relations
        ]

    def verify_single(
        self,
        relation: JEVExtractedRelation,
        raw_document_text: str,
        strict: bool = True,
    ) -> NLIResult:
        return verify_quotebound(relation, raw_document_text, strict=strict, backend=self.backend)
