export type EntityCategory =
  | "Person"
  | "Organization"
  | "Location"
  | "MilitarySystem"
  | "Component"
  | "NarrativeFrame"
  | "Event"
  | "LegalDocument"
  | "FinancialIdentifier"
  | "TelegramChannel"
  | "Website"
  | "PhoneNumber"
  | "EmailAddress"
  | "Infrastructure"
  | "Group"
  | "PoliticalParty"
  | "ServiceProvider"
  | "RiskIndicator"
  | "JobType";

export type RelationType =
  | "OWNS_CONTROLS"
  | "SUPPLIES_COMPONENT"
  | "MANUFACTURES"
  | "FUNDS"
  | "AFFILIATED_WITH"
  | "AMPLIFIES_NARRATIVE"
  | "CONTRADICTS_CLAIM"
  | "PARTICIPATED_IN"
  | "SANCTIONED_UNDER"
  | "HIERARCHY_PARENT_OF"
  | "LOCATED_IN"
  | "OPERATES_FROM"
  | "RECRUITS_FROM"
  | "ATTACKED"
  | "COMMUNICATES_WITH";

/** Sharing restriction carried by entities and claims. */
export type Sensitivity = "public" | "sensitive" | "restricted";

export type AdmiraltyReliability =
  | "A_COMPLETELY_RELIABLE"
  | "B_USUALLY_RELIABLE"
  | "C_FAIRLY_RELIABLE"
  | "D_NOT_USUALLY_RELIABLE"
  | "E_UNRELIABLE"
  | "F_CANNOT_BE_JUDGED";

export interface JEVExtractedEntity {
  canonical_name: string;
  category: EntityCategory;
  aliases?: string[];
  deterministic_ids?: Record<string, string>;
  summary_fact: string;
  evidence?: VerbatimSpan;
  confidence?: number;
}

export interface JEVExtractedRelation {
  source_entity: string;
  target_entity: string;
  relation_type: RelationType;
  temporal_valid_from?: string;
  temporal_valid_to?: string;
  nli_entailment_score: number;
  swarm_consensus_count: number;
  evidence?: VerbatimSpan;
  weight?: number;
}

export interface VerbatimSpan {
  source_doc_sha256: string;
  exact_quote: string;
  start_char: number;
  end_char: number;
}

export interface JEVDistillationBundle {
  doc_sha256: string;
  lande_hub_terms: string[];
  metrics: JEVAttackIndexMetrics;
  entities: JEVExtractedEntity[];
  relations: JEVExtractedRelation[];
}

export interface JEVAttackIndexMetrics {
  emotional_intensity: number;
  manipulative_markers: string[];
  slop_probability: number;
  admiralty_reliability: AdmiraltyReliability;
  credibility_rank: number;
}

export interface Entity {
  id: string;
  canonical_name: string;
  category: string;
  aliases?: string[];
  external_ids?: Record<string, string>;
  summary?: string;
  wiki_markdown?: string;
  confidence_score?: number;
  lifecycle_state?: string;
  hvg_centrality?: number;
  sensitivity?: Sensitivity;
  updated_at?: string;
}

export interface Claim {
  claim_id: string;
  statement: string;
  predicate: string;
  confidence?: number;
  nli_entailment?: number;
  swarm_votes?: number;
  status?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation_type: string;
  weight?: number;
  is_disputed?: boolean;
  claim_id?: string | null;
  claim_statement?: string | null;
  claim_confidence?: number | null;
  entailment?: number | null;
  evidence?: {
    exact_quote: string;
    source_sha256: string;
    nli_score?: number | null;
  }[];
}

export interface SubgraphEntity {
  id: string;
  canonical_name: string;
  category?: string;
  confidence?: number;
  summary?: string;
  lifecycle_state?: string;
}

export interface SubgraphResponse {
  entities: SubgraphEntity[];
  edges: GraphEdge[];
}

export interface WikiPage {
  slug: string;
  content: string;
  frontmatter: Record<string, unknown>;
}

export interface AttackIndexTimeSeries {
  days: number;
  topic?: string | null;
  time_series: {
    date: string;
    avg_attack_index: number;
    doc_count: number;
    terms: string[];
  }[];
}

export interface ContradictionAlert {
  entity_id?: string;
  entity_name?: string;
  claim_a?: string;
  claim_b?: string;
  statement_a?: string;
  statement_b?: string;
  severity?: number;
  detected_at?: string;
}

export interface LintReport {
  contradictions: ContradictionAlert[];
  decay_issues: {
    claim_id: string;
    old_confidence: number;
    new_confidence: number;
    delta_days: number;
  }[];
  wave_alerts: {
    timestamp?: string;
    term?: string;
    z_score: number;
    attack_index: number;
  }[];
  structural_gaps: {
    entity_id: string;
    canonical_name: string;
    category?: string;
    gap_type: string;
  }[];
  timestamp: string;
}

export interface EntityCounts {
  total: number;
}

export interface DocumentCounts {
  count: number
}

/** Dashboard statistics from the /stats/dashboard backend endpoint. */
export interface DashboardStats {
  sources: {
    total: number
    admiralty_breakdown: Record<string, number>
    quarantined: number
  }
  entities: {
    total: number
    by_category: Record<string, number>
  }
  claims: {
    total: number
    evidenced: number
    confidence_distribution: {
      high: number
      medium: number
      low: number
    }
  }
  relations: {
    relates_to: number
    reprints: number
  }
  contradictions: {
    count: number
  }
  osint: {
    open_tickets: number
    synth_concepts: number
  }
  quality_metrics: {
    extraction_success_rate: number
    average_nli_score: number
    total_claims_with_nli: number
  }
  activity: {
    recent_ingestions: string[]
    last_update?: string
  }
}
