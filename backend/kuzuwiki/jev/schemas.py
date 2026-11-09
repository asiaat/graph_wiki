"""Core JEV Type-Safe Data Contracts (Pydantic v2).
All agents must bind to these schemas. Any JEV output failing validation is rejected.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

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
    # --- Extensions required by open-source corpora (see osint_berlin26) ---
    #: A messaging/forum channel (Telegram, Matrix, ...).
    TELEGRAM_CHANNEL = "TelegramChannel"
    #: A website or domain.
    WEBSITE = "Website"
    #: A phone number as an identifier.
    PHONE_NUMBER = "PhoneNumber"
    #: An email address as an identifier.
    EMAIL_ADDRESS = "EmailAddress"
    #: Physical or technical infrastructure (substations, hosting, depots).
    INFRASTRUCTURE = "Infrastructure"
    #: An informal or clandestine group without legal personality.
    GROUP = "Group"
    #: A political party or movement.
    POLITICAL_PARTY = "PoliticalParty"
    #: A commercial or industrial service provider.
    SERVICE_PROVIDER = "ServiceProvider"
    #: A risk marker or exploitation indicator.
    RISK_INDICATOR = "RiskIndicator"
    #: An occupation or job type.
    JOB_TYPE = "JobType"


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
    # --- Extensions required by open-source corpora (see osint_berlin26) ---
    #: Physical or administrative location of an entity.
    LOCATED_IN = "LOCATED_IN"
    #: An entity operates from / out of another entity or place.
    OPERATES_FROM = "OPERATES_FROM"
    #: Recruitment or labour-channel linkage.
    RECRUITS_FROM = "RECRUITS_FROM"
    #: An entity was the target of an attack.
    ATTACKED = "ATTACKED"
    #: Direct communication or contact between entities.
    COMMUNICATES_WITH = "COMMUNICATES_WITH"


class SourceType(str, Enum):
    """The kind of document being ingested.

    The Admiralty classifier grades *sources*, so it needs to know what kind
    of source it is looking at. An analyst assessment has no publisher and no
    web domain, and rating it "cannot be judged" would be wrong.
    """

    WEB_ARTICLE = "web_article"
    ANALYST_REPORT = "analyst_report"
    OFFICIAL_RECORD = "official_record"
    MEDIA = "media"
    INTELLIGENCE = "intelligence"


class Sensitivity(str, Enum):
    """How freely a record may be shared.

    ``SENSITIVE`` covers direct contact identifiers and risk markers;
    ``RESTRICTED`` covers persons of interest and allegations about them.
    """

    PUBLIC = "public"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


#: Categories whose records are contact data or risk markers by nature.
SENSITIVE_CATEGORIES: frozenset[EntityCategory] = frozenset(
    {
        EntityCategory.PHONE_NUMBER,
        EntityCategory.EMAIL_ADDRESS,
        EntityCategory.TELEGRAM_CHANNEL,
        EntityCategory.RISK_INDICATOR,
    }
)


def default_sensitivity_for(category: EntityCategory) -> Sensitivity:
    """Derive the default sharing restriction for an entity category.

    Persons are marked sensitive rather than restricted: a named individual is
    not itself a disclosure risk, but an allegation *about* one is, and the
    importer can escalate a person of interest to ``RESTRICTED``.
    """
    if category in SENSITIVE_CATEGORIES:
        return Sensitivity.SENSITIVE
    if category == EntityCategory.PERSON:
        return Sensitivity.SENSITIVE
    return Sensitivity.PUBLIC


class VerbatimSpan(BaseModel):
    """Immutable pointer to a character span in the raw archive.

    ``exact_quote`` is the authoritative artefact: the verifier locates it in
    the raw document and re-derives the character offsets. Offsets supplied by
    an extractor are therefore advisory only and default to ``0``.
    """

    source_doc_sha256: str
    exact_quote: str = Field(
        ..., min_length=15, max_length=4096, description="Exact substring from raw document"
    )
    start_char: int = Field(0, ge=0)
    end_char: int = Field(0, ge=0)

    @field_validator("exact_quote")
    @classmethod
    def quote_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("exact_quote must not be empty whitespace")
        return v


class JEVExtractedEntity(BaseModel):
    canonical_name: str = Field(..., min_length=1, max_length=512)
    category: EntityCategory
    aliases: list[str] = Field(default_factory=list, max_length=50)
    deterministic_ids: dict[str, str] = Field(
        default_factory=dict, description="e.g., {'tax_id': '...', 'imo': '...', 'hs_code': '...'}"
    )
    summary_fact: str = Field(..., min_length=1, max_length=4096)
    evidence: VerbatimSpan
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Sharing restriction. Defaults are derived from the category when unset.
    sensitivity: Sensitivity | None = None


class JEVExtractedRelation(BaseModel):
    source_entity: str = Field(..., min_length=1, max_length=512)
    target_entity: str = Field(..., min_length=1, max_length=512)
    relation_type: RelationType
    temporal_valid_from: str | None = Field(None, description="ISO-8601 date or YYYY-MM")
    temporal_valid_to: str | None = Field(None, description="ISO-8601 date or YYYY-MM")
    nli_entailment_score: float = Field(..., ge=0.0, le=1.0)
    swarm_consensus_count: int = Field(..., ge=1, le=5)
    evidence: VerbatimSpan
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Sharing restriction for the claim itself.
    sensitivity: Sensitivity | None = None

    @model_validator(mode="after")
    def validate_temporal(self):
        if self.temporal_valid_from and self.temporal_valid_to:
            if self.temporal_valid_from > self.temporal_valid_to:
                raise ValueError("temporal_valid_from must not exceed temporal_valid_to")
        return self


class JEVAttackIndexMetrics(BaseModel):
    emotional_intensity: float = Field(..., ge=0.0, le=1.0)
    manipulative_markers: list[str] = Field(
        default_factory=list, description="Detected euphemisms, strategic framing, fear triggers"
    )
    slop_probability: float = Field(..., ge=0.0, le=1.0)
    admiralty_reliability: AdmiraltyReliability
    credibility_rank: int = Field(..., ge=1, le=6)


class JEVDistillationBundle(BaseModel):
    """Top-level output from the full JEV pipeline (Gatekeeper → HVG → Swarm)."""

    doc_sha256: str
    lande_hub_terms: list[str]
    metrics: JEVAttackIndexMetrics
    entities: list[JEVExtractedEntity]
    relations: list[JEVExtractedRelation]
    #: Directed visibility-graph edges, persisted as the DomainTerm hierarchy.
    hvg_edges: list[dict[str, Any]] = Field(default_factory=list)
    #: Prominence weight per term.
    term_weights: dict[str, float] = Field(default_factory=dict)
    #: Terms whose frequency spiked inside the document.
    burst_terms: list[str] = Field(default_factory=list)

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
    title: str | None = None
    domain: str | None = None
    published_at: str | None = None
    mime_type: str | None = None
    #: Analysis mode (e.g. ``COGNITIVE_WARFARE_STUDY``). Slop quarantine is
    #: waived for modes that deliberately study manipulative material.
    domain_mode: str | None = None
    #: Marks the document as an artifact kept for disinformation study.
    is_adversarial_artifact: bool = False
    #: What kind of source this is. Drives the Admiralty rating.
    source_type: SourceType = SourceType.WEB_ARTICLE
    #: Which domain pack governs this document (see ``config/domain_schemas``).
    analysis_domain: str | None = None
    #: Sharing restriction for the document as a whole.
    sensitivity: Sensitivity = Sensitivity.PUBLIC
