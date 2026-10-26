export type EntityCategory =
  | "Person"
  | "Organization"
  | "Location"
  | "MilitarySystem"
  | "Component"
  | "NarrativeFrame"
  | "Event"
  | "LegalDocument"
  | "FinancialIdentifier";

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
  | "HIERARCHY_PARENT_OF";

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
}

export interface SubgraphResponse {
  paths: any[];
}

export interface AttackIndexTimeSeries {
  days: number;
  time_series: {
    date: string;
    avg_attack_index: number;
    doc_count: number;
    terms: string[];
  }[];
}