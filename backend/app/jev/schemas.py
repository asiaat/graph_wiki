"""Core JEV Type-Safe Data Contracts (Pydantic v2).
All agents must bind to these schemas. Any JEV output failing validation is rejected.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, Field, field_validator, model_validator


class AdmiraltyReliability(str, Enum):
    A = "A_COMPLETELY_RELIABLE"
    B = "B_USUALLY_RELIABLE"
    C = "C_FAIRLY_RELIABLE"
    D = "D_NOT_USUALLY_RELIABLE"
    E = "E_UNRELIABLE"
    F = "F_CANNOT_BE_JUDGED"


class EntityCategory(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    MILITARY_SYSTEM = "MilitarySystem"
    COMPONENT = "Component"
    NARRATIVE_FRAME = "NarrativeFrame"
    EVENT = "Event"
    LEGAL_DOCUMENT = "LegalDocument"
    FINANCIAL_IDENTIFIER = "FinancialIdentifier"


class RelationType(str, Enum):
    OWNS_CONTROLS = "OWNS_CONTROLS"
    SUPPLIES_COMPONENT = "SUPPLIES_COMPONENT"
    MANUFACTURES = "MANUFACTURES"
    FUNDS = "FUNDS"
    AFFILIATED_WITH = "AFFILIATED_WITH"
    AMPLIFIES_NARRATIVE = "AMPLIFIES_NARRATIVE"
    CONTRADICTS_CLAIM = "CONTRADICTS_CLAIM"
    PARTICIPATED_IN = "PARTICIPATED_IN"
    SANCTIONED_UNDER = "SANCTIONED_UNDER"
    HIERARCHY_PARENT_OF = "HIERARCHY_PARENT_OF"


class VerbatimSpan(BaseModel):
    """Immutable pointer to a character span in the raw archive."""

    source_doc_sha256: str
    exact_quote: str = Field(
        ..., min_length=15, max_length=4096, description="Exact substring from raw document"
    )
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., gt=0)

    @field_validator("exact_quote")
    @classmethod
    def quote_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("exact_quote must not be empty whitespace")
        return v


class JEVExtractedEntity(BaseModel):
    canonical_name: str = Field(..., min_length=1, max_length=512)
    category: EntityCategory
    aliases: List[str] = Field(default_factory=list, max_length=50)
    deterministic_ids: dict[str, str] = Field(
        default_factory=dict, description="e.g., {'tax_id': '...', 'imo': '...', 'hs_code': '...'}"
    )
    summary_fact: str = Field(..., min_length=1, max_length=4096)
    evidence: VerbatimSpan
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class JEVExtractedRelation(BaseModel):
    source_entity: str = Field(..., min_length=1, max_length=512)
    target_entity: str = Field(..., min_length=1, max_length=512)
    relation_type: RelationType
    temporal_valid_from: Optional[str] = Field(None, description="ISO-8601 date or YYYY-MM")
    temporal_valid_to: Optional[str] = Field(None, description="ISO-8601 date or YYYY-MM")
    nli_entailment_score: float = Field(..., ge=0.0, le=1.0)
    swarm_consensus_count: int = Field(..., ge=1, le=5)
    evidence: VerbatimSpan
    weight: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_temporal(self):
        if self.temporal_valid_from and self.temporal_valid_to:
            if self.temporal_valid_from > self.temporal_valid_to:
                raise ValueError("temporal_valid_from must not exceed temporal_valid_to")
        return self


class JEVAttackIndexMetrics(BaseModel):
    emotional_intensity: float = Field(..., ge=0.0, le=1.0)
    manipulative_markers: List[str] = Field(
        default_factory=list, description="Detected euphemisms, strategic framing, fear triggers"
    )
    slop_probability: float = Field(..., ge=0.0, le=1.0)
    admiralty_reliability: AdmiraltyReliability
    credibility_rank: int = Field(..., ge=1, le=6)


class JEVDistillationBundle(BaseModel):
    """Top-level output from the full JEV pipeline (Gatekeeper → HVG → Swarm)."""

    doc_sha256: str
    lande_hub_terms: List[str]
    metrics: JEVAttackIndexMetrics
    entities: List[JEVExtractedEntity]
    relations: List[JEVExtractedRelation]

    @model_validator(mode="after")
    def enforce_nli_threshold(self):
        """Hard reject: NLI entailment must be >= 0.85 for all relations."""
        self.relations = [r for r in self.relations if r.nli_entailment_score >= 0.85]
        return self

    def reject_slop(self) -> bool:
        """Returns True if the entire document should be quarantined as slop."""
        return self.metrics.slop_probability > 0.65


class RawDocumentPayload(BaseModel):
    """Input to GatekeeperSlopAgent."""

    content: str | None = None
    uri: str | None = None
    title: Optional[str] = None
    domain: Optional[str] = None
    published_at: Optional[str] = None
    mime_type: Optional[str] = None
