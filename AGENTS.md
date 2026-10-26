# AGENTS.md — Swarm of Virtual Experts & JEV Agent Specification
**System:** KuzuWiki-OSINT  
**Methodology:** Prof. D. Lande’s *Swarm of Virtual Experts* + Karpathy *Ingest/Compile/Query/Lint* Loop + Type-Safe JEV Classifiers  

---

## 1. Agent Governance Philosophy
In KuzuWiki-OSINT, agents do **not** chat aimlessly or generate free-form prose directly into the database. Every agent operates as a bounded compiler pass over **KùzuDB** and the **Immutable Source Store**.

1. **Human as Mentor of the Swarm (Lande Principle):** Autonomous agents propose graph complications, entity merges, and OSINT expansions. High-confidence, deterministic facts auto-commit; structural ontology shifts or contradictory claims enter the **Async Mentor Review Queue**.
2. **Type-Safe JEV Contract:** Agents must emit responses strictly conforming to compiled `Pydantic v2` / `BAML` JEV schemas. Any output failing schema validation, verbatim substring alignment, or NLI entailment is rejected before touching KùzuDB.
3. **Epistemic Humility Rule:** If the compiled graph lacks sufficient verified evidence ($Confidence < 0.70$) to answer a query or bridge two entities, the agent **must** output `INSUFFICIENT_VERIFIED_EVIDENCE` and spawn an `OSINTGapTicket` rather than extrapolating.

---

## 2. Agent Topology & Roles

```
                     +---------------------------------------+
                     |     HUMAN ANALYST (Swarm Mentor)      |
                     +-------------------+-------------------+
                                         |
                                         v
                     +---------------------------------------+
                     |   ORCHESTRATOR (LangGraph / AgentFlow)|
                     +---+-----------+-----------+-----------+
                         |           |           |
       +-----------------+     +-----+-----+     +-----------------+
       v                       v           v                       v
+--------------+       +---------------+ +---------------+ +---------------+
| 1. Gatekeeper|       | 2. Lande HVG  | | 3. JEV Swarm  | | 4. Graph-Wiki |
| & Anti-Slop  |------>| & Term Net    |->|  Extractors   |->|   Compiler    |
|    Agent     |       |    Agent      | |  (N=3..5)     | |    Agent      |
+--------------+       +---------------+ +---------------+ +-------+-------+
                                                                   |
                                         +-------------------------+
                                         v
                     +---------------------------------------+
                     |    KÙZUDB PROPERTY GRAPH & WIKI       |
                     +---+-------------------------------+---+
                         |                               |
                         v                               v
               +-------------------+           +-------------------+
               | 5. Adversarial    |           | 6. OSINT Compli-  |
               | Linter & Attack-  |---------->| cator & Deep      |
               | Index Agent       |  Spawns   | Research Agent    |
               +-------------------+  Tickets  +-------------------+
```

---

### Agent 1: `GatekeeperSlopAgent` (Pre-Ingest Filter & Admiralty Classifier)
* **Mission:** Protect the knowledge base from AI slop, SEO spam, circular reporting, and unverified propaganda before compilation begins.
* **Inputs:** Raw ingested file or scraped URL (`RawDocumentPayload`).
* **Theoretical & JEV Models Used:**
  * **Synthetic Slop Classifier (`JEVSlopModel`):** Evaluates token perplexity variance, burstiness, clichés, and information density ratio ($\text{Atomic Claims} / \text{Token Count}$).
  * **Echo/Reprint Detector (Lande InfoStream Method):** Computes MinHash / SimHash shingles against existing `SourceDocument` nodes in KùzuDB to detect exact or near-exact reprints and syndicated wire copies.
  * **Admiralty Code Classifier:** Assigns initial Source Reliability ($A\text{--}F$) and Information Credibility ($1\text{--}6$).
* **Hard Rules:**
  * If `slop_probability > 0.65` AND domain mode $\neq$ `COGNITIVE_WARFARE_STUDY`, reject document to `/quarantine/slop/`.
  * If document is a reprint of an existing source, do **not** increment independent corroboration count; instead, create a `[:REPRINTS {delay_minutes}]` edge between media outlets for influence network mapping.

---

### Agent 2: `LandeNetworkAgent` (Deterministic HVG & Directed Term Hierarchy Builder)
* **Mission:** Construct the mathematical backbone of a document or corpus prior to LLM interpretation using Prof. Lande’s complex network algorithms.
* **Inputs:** Cleaned text tokens and sentence sequence from `GatekeeperSlopAgent`.
* **Algorithms:**
  1. **TF-IDF / Burst Weighting:** Assigns statistical weight $w(t_i)$ to domain terms across the sliding window.
  2. **Horizontal Visibility Graph (HVG):** Converts the sequential term series into an undirected visibility graph where nodes $i$ and $j$ are connected iff:
     $$w(t_k) < \min\big(w(t_i), w(t_j)\big) \quad \forall k \in (i, j)$$
  3. **Directed Weighted Network of Terms:** Calculates asymmetric conditional probability and positional precedence to orient edges ($t_A \rightarrow t_B$, where $t_A$ is the general/governing concept and $t_B$ is the subordinate/specific term).
* **Output (`LandeTermBackbone`):** A deterministic list of top-ranked hub terms, natural taxonomic hierarchies, and anomalous keyword bursts passed as mandatory structural constraints to the JEV Swarm.

---

### Agent 3: `JEVSwarmExtractor` (Virtual Expert Swarm — $N=3$ Personas)
* **Mission:** Distill unstructured documents into strictly typed nodes, directed edges, and atomic claims using Lande’s *Swarm of Virtual Experts* pattern.
* **Swarm Composition:**
  * **Expert Alpha (`ConservativeAuditor`):** Temperature $0.0$; extracts only explicit, legally/factually stated entities, serial numbers, registration IDs, dates, and financial figures.
  * **Expert Beta (`RelationalInvestigator`):** Temperature $0.2$; focuses on organizational links, supply-chain dependencies, beneficial ownership, and geopolitical affiliations anchored in `LandeTermBackbone`.
  * **Expert Gamma (`CognitiveWarfareAnalyst`):** Temperature $0.1$; extracts narrative frames, emotional manipulation markers, euphemisms, and strategic blame attribution (Attack-Index features).
* **Consensus & JEV Verification Engine:**
  * Let $E_\alpha, E_\beta, E_\gamma$ be the sets of extracted triples $(u, r, v)$ from the three virtual experts.
  * The **Consensus Aggregator** computes edge weight:
    $$W(u, r, v) = \sum_{m \in \{\alpha, \beta, \gamma\}} \omega_m \cdot \mathbb{I}\big((u, r, v) \in E_m\big) \cdot \text{NLI}_{\text{score}}(u, r, v, \text{quote})$$
  * **Verbatim Citation Gate:** A deterministic Python validator checks `assert quote in raw_document_text`. If false, the triple is immediately discarded.

---

### Agent 4: `GraphWikiCompilerAgent` (KùzuDB Upsert & Wiki Maintainer)
* **Mission:** Act as the Karpathy "Knowledge Compiler." Integrate verified JEV triples into **KùzuDB** and compile/update the corresponding human-readable Markdown Wiki dossiers.
* **Operations:**
  1. **Entity Resolution (Write-Time Deduplication):** Queries KùzuDB using hybrid Vector Cosine Similarity ($>0.92$) + Jaro-Winkler alias matching + deterministic identifiers (e.g., IMO number, Tax ID, Corporate Registration Number) to resolve extracted entities against existing graph nodes.
  2. **Cypher Graph Upsert:** Executes parameterized Cypher `MERGE` statements to create or update `Entity`, `Concept`, `Claim`, and `Evidence` nodes and their typed edges.
  3. **Incremental Wiki Compilation:** Re-compiles the `.md` dossier stored on the node (`Entity.wiki_markdown` and mirrored in `/data/wiki/{slug}.md`).
     * Enforces YAML frontmatter (`slug`, `kuzu_id`, `entity_type`, `confidence_score`, `admiralty_rating`, `sources`, `last_compiled`).
     * Embeds `[[slug]]` bidirectional wikilinks matching KùzuDB edges.
     * Appends a structured **Disputed & Contradictory Claims** section if conflicting edges exist.

---

### Agent 5: `AdversarialLinterAgent` (Graph Health, Contradiction & Attack-Index Monitor)
* **Mission:** Continuously audit KùzuDB for logical contradictions, epistemic decay, structural gaps, and cognitive warfare waves.
* **Scheduled & Triggered Checks:**
  1. **Semantic Contradiction Detection:** Runs Cypher queries to find pairs of `Claim` nodes attached to the same `Entity` with opposing predicates or temporal overlaps (e.g., Company X claims "exited market in 2024" vs. Customs log showing "shipment in 2026"). Flags both with a `[:CONTRADICTS {severity}]` edge.
  2. **Ebbinghaus Confidence Decay:** Applies temporal decay to dynamic claims (e.g., corporate board seats, front-line unit positions) that have not been re-verified within $\Delta t$ days:
     $$C(t) = C_0 \cdot e^{-\lambda (t - t_{\text{verified}})}$$
  3. **Attack-Index Wave Detection:** Monitors time-series ingestion of `NarrativeFrame` nodes. If frequency $\frac{dN}{dt}$ exceeds $2.5\sigma$ over baseline while `Echo/Reprint` ratio spikes, raises a `CognitiveOperationAlert`.
  4. **Structural Gap Identification (Adamic-Adar & Bridge Analysis):** Identifies weakly connected subgraphs or high-betweenness nodes lacking primary source corroboration, generating `ComplicationTicket` nodes in KùzuDB.

---

### Agent 6: `OSINTComplicatorAgent` (Autonomous Deep Research & Knowledge Enhancer)
* **Mission:** Fulfill the system’s core imperative—*to complicate and enhance the expert system continuously* by hunting for missing facts, verifying uncorroborated claims, and expanding entity subgraphs.
* **Trigger:** Consumes `ComplicationTicket` nodes from KùzuDB or direct user *"Complicate Subgraph"* commands.
* **Autonomous Loop:**
  1. **Hypothesis & Dork Formulation:** Reads the local $k$-hop neighborhood in KùzuDB around the target entity. Formulates targeted search queries (e.g., Google/SearXNG dorks, OpenCorporates/sanctions lookups, arXiv/patent queries, aviation/maritime/customs database queries per Lande’s Deep Web OSINT methodology).
  2. **Multi-Source Retrieval:** Executes sandboxed scraping via SearXNG / Tavily / Playwright / Archive.org APIs.
  3. **Strict Re-Entry:** Feeds discovered documents back into **Agent 1 (`GatekeeperSlopAgent`)**. Never writes directly to the graph; all web findings must survive the full Anti-Slop + Lande HVG + JEV Swarm pipeline.

---

## 3. Core JEV Type-Safe Data Contracts (Python / Pydantic Specification)

All agents must bind to the following canonical JEV schemas:

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

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
    MILITARY_SYSTEM = "MilitarySystem"       # e.g., UAV model, EW system
    COMPONENT = "Component"                 # e.g., Microcontroller, optical sensor
    NARRATIVE_FRAME = "NarrativeFrame"       # Cognitive warfare theme
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
    HIERARCHY_PARENT_OF = "HIERARCHY_PARENT_OF" # From Lande HVG

class VerbatimSpan(BaseModel):
    source_doc_sha256: str
    exact_quote: str = Field(..., min_length=15, description="Exact substring from raw document")
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., gt=0)

class JEVExtractedEntity(BaseModel):
    canonical_name: str
    category: EntityCategory
    aliases: List[str] = Field(default_factory=list)
    deterministic_ids: dict[str, str] = Field(
        default_factory=dict,
        description="e.g., {'tax_id': '...', 'imo': '...', 'hs_code': '...'}"
    )
    summary_fact: str
    evidence: VerbatimSpan

class JEVExtractedRelation(BaseModel):
    source_entity: str
    target_entity: str
    relation_type: RelationType
    temporal_valid_from: Optional[str] = Field(None, description="ISO-8601 date or YYYY-MM")
    temporal_valid_to: Optional[str] = Field(None, description="ISO-8601 date or YYYY-MM")
    nli_entailment_score: float = Field(..., ge=0.0, le=1.0)
    swarm_consensus_count: int = Field(..., ge=1, le=5)
    evidence: VerbatimSpan

class JEVAttackIndexMetrics(BaseModel):
    emotional_intensity: float = Field(..., ge=0.0, le=1.0)
    manipulative_markers: List[str] = Field(
        default_factory=list,
        description="Detected euphemisms, strategic framing, fear triggers"
    )
    slop_probability: float = Field(..., ge=0.0, le=1.0)
    admiralty_reliability: AdmiraltyReliability
    credibility_rank: int = Field(..., ge=1, le=6)

class JEVDistillationBundle(BaseModel):
    doc_sha256: str
    lande_hub_terms: List[str]
    metrics: JEVAttackIndexMetrics
    entities: List[JEVExtractedEntity]
    relations: List[JEVExtractedRelation]

    @model_validator(mode="after")
    def reject_slop_and_weak_entailment(self):
        # Enforce hard verification threshold on all relations
        self.relations = [
            r for r in self.relations if r.nli_entailment_score >= 0.85
        ]
        return self
```