# Product Requirements Document (PRD): KuzuWiki-OSINT
**System Name:** KuzuWiki-OSINT (Graph-Compiled Expert Intelligence & Anti-Slop Knowledge System)  
**Version:** 1.0.0  
**Status:** Architecture & Specification  
**Target Domains:** Hybrid Warfare Analysis, Drone Industry Supply Chains, Political Influence Operations, Corporate Malfeasance & OSINT Investigations  

---

## 1. Executive Summary & Vision
Traditional Retrieval-Augmented Generation (RAG) systems are stateless, rediscovering fragments of information from scratch on every query and failing to connect multi-hop facts across hundreds of documents. Conversely, standard LLM-generated summaries suffer from hallucination, unverified claims, and recursive "AI slop."

**KuzuWiki-OSINT** adapts the **LLM Wiki compilation pattern** (compiling raw sources once into a persistent, self-evolving knowledge base rather than retrieving raw chunks at query time) and replaces flat Markdown-only link structures with an embedded, high-performance **KùzuDB** property graph + vector + full-text engine. 

Anchored in the theoretical foundations of **Prof. Dmytro Lande** (Horizontal Visibility Graphs, Directed Weighted Networks of Terms, Swarm of Virtual Experts, InfoStream/Attack-Index wave anomaly detection, and Decision Support hierarchies) and enforced by **Type-Safe JEV (Joint Extraction & Verification) Classifier Models** (Pydantic/BAML/Instructor constrained schemas + deterministic classifiers), the system acts as a living **Domain Expert System**. It continuously complicates, deepens, and verifies its own knowledge graph via ingested documents and autonomous OSINT web expansion while enforcing a zero-tolerance gate against synthetic slop and disinformation.

---

## 2. Theoretical Foundation (Prof. Dmytro Lande Framework)
The system's analytical rigor is directly derived from Prof. Dmytro Lande’s body of work in information security, OSINT, and complex semantic networks:

1. **Horizontal Visibility Graphs (HVG) & Natural Term Hierarchies:**
   * Before an LLM summarizes a text, the deterministic NLP pipeline maps time-series or sequential token weights into a Horizontal Visibility Graph. Two terms $t_i$ and $t_j$ share visibility if all intermediate terms $t_k$ ($i < k < j$) have weight $w_k < \min(w_i, w_j)$.
   * This extracts scale-free topological backbones of text and determines natural hierarchical directionality ($A \rightarrow B$) between domain concepts without LLM hallucination.
2. **Swarm of Virtual Experts (Consensus Semantic Networking):**
   * Single-pass LLM extraction yields sparse, biased networks. Following Lande & Strashnoy’s *Swarm of Virtual Experts* methodology, the system queries heterogeneous agent personas and temperatures in parallel over the same source material.
   * Only entities and edges achieving consensus weight $W_{ij} \ge \tau$ across the virtual swarm are committed to KùzuDB, while humans act as "Mentors of the Swarm."
3. **Attack-Index & Information Flow Lifecycle Dynamics:**
   * Information operations and hybrid warfare narratives follow non-linear wave dynamics (modeled via logistic equations and cellular automata).
   * The system calculates an **Attack-Index** score per topic cluster, tracking emotional triggers, euphemisms, strategic framing, reprint cascades, and sudden frequency anomalies ($\Delta f / \Delta t$) to separate organic reporting from coordinated cognitive warfare.
4. **Strict Verbatim Provenance (InfoStream RAG Standard):**
   * Every synthesized wiki claim and graph edge must maintain an immutable cryptographic and character-offset pointer to an archived primary source fragment, ensuring suitability for official intelligence briefs and legal/regulatory audits.

---

## 3. Core Functional Pillars

### 3.1. Four-Phase Knowledge Compilation Lifecycle
Instead of stateless RAG, KuzuWiki-OSINT operates a continuous compiler loop:
1. **INGEST (Immutable Archive + JEV Gate):** Raw PDFs, OSINT scrapes, corporate registries, and Telegram/web dumps are hashed (`SHA-256`), archived immutably, and passed through the **Anti-Slop & JEV Classifier Gate**.
2. **COMPILE (Graph + Wiki Synthesis):** Validated atomic claims, typed entities, and directed relationships are upserted into **KùzuDB**. Corresponding structured Markdown wiki pages (synchronized with KùzuDB `Concept` and `Entity` nodes) are incrementally compiled and updated.
3. **QUERY & COMPOUND:** Analysts query the compiled KùzuDB graph + wiki articles using hybrid Cypher traversal + Vector + BM25 search. High-value analytical answers are **filed back (`--save`)** into the graph as `DerivedSynthesis` nodes.
4. **LINT & AUTONOMOUS COMPLICATION:** Background agents scan KùzuDB for structural orphans, temporal decay, conflicting claims, and low-density subgraphs. They formulate targeted OSINT queries, search the deep/surface web, and ingest new verified evidence to continuously complicate and refine the domain model.

### 3.2. Type-Safe JEV (Joint Extraction & Verification) Classifiers
Every document distillation and graph mutation is governed by **Type-Safe JEV Models**:
* **Strict Schema Enforcement:** Powered by Python `Pydantic v2` + `Instructor` / `BAML` + local DeBERTa/GLiNER cross-encoders. No free-text LLM output is ever parsed with brittle regex.
* **Three-Stage JEV Pipeline:**
  1. **J — Joint Entity & Relation Extraction:** Simultaneous extraction of domain-typed nodes (`Person`, `Organization`, `DroneComponent`, `SanctionRecord`, `NarrativeFrame`) and typed directed edges (`SUPPLIES_TO`, `BENEFICIAL_OWNER_OF`, `AMPLIFIES_NARRATIVE`, `CONTRADICTS`) within a single type-safe AST call.
  2. **E — Epistemic & Slop Classification:** Deterministic + neural classification of source credibility (NATO Admiralty Scale $A1\text{--}F6$), AI-slop probability (perplexity/burstiness/stylometric watermarks), and manipulative framing markers.
  3. **V — Verbatim Grounding & Entailment Verification:** Cross-encoder Natural Language Inference (NLI) checks that every extracted triple $(u, r, v)$ is strictly entailed by the exact character span `[start_char:end_char]` in the immutable source document.

---

## 4. Target Use Cases & Domain Profiles

| Domain Focus | Primary Entities (KùzuDB Nodes) | Key JEV Relations (KùzuDB Edges) | Analytical Output |
| :--- | :--- | :--- | :--- |
| **Hybrid & Cognitive Warfare** | `NarrativeFrame`, `MediaOutlet`, `BotNetwork`, `GeopoliticalEvent`, `Actor` | `AMPLIFIES`, `REPRINTS_FROM`, `EXPLOITS_BIAS`, `ATTRIBUTED_TO` | Attack-Index wave charts, narrative mutation trees, zero-patient source identification. |
| **Drone Industry & Supply Chains** | `UAVModel`, `SubComponent`, `Manufacturer`, `Distributor`, `CustomsHSCode` | `CONTAINS_PART`, `MANUFACTURED_BY`, `TRANSITED_THROUGH`, `SANCTIONED_BY` | Multi-hop sanction evasion paths, Chokepoint centrality analysis, BOM (Bill of Materials) wiki dossiers. |
| **Political Influence & Lobbying** | `Politician`, `ThinkTank`, `Donor`, `Legislation`, `Foundation` | `FUNDS`, `CO_AUTHORS`, `BOARD_MEMBER_OF`, `LOBBIES_FOR` | Hidden influence pathfinding, temporal alignment of donations vs. legislative voting. |
| **Corporate OSINT & Malactivity** | `Company`, `BeneficialOwner`, `OffshoreEntity`, `Litigation`, `WalletAddress` | `OWNS_SHARE`, `SHARES_DIRECTOR_WITH`, `REGISTERED_AT`, `TRANSACTED_WITH` | Shell company cluster detection (Louvain), beneficial ownership unrolling, red-flag audit reports. |

---

## 5. User Interface Requirements (TypeScript, React, Tailwind CSS)
The frontend is an analyst-grade workbench combining an Obsidian-like compiled Wiki IDE with a Palantir/Gephi-style Graph & Time-Series Intelligence Console:
1. **Tri-Pane Knowledge Workbench:**
   * **Left Pane:** Domain Ontology Tree, Immutable Source Vault, and Live Autonomous Agent Queue.
   * **Center Pane:** Synchronized Dual-View—toggle or split between the **Compiled Wiki Article** (Markdown with interactive `[[Entity]]` pills and hoverable verbatim source citations) and the **Interactive KùzuDB Graph Canvas** (WebGL/Sigma.js force-directed and hierarchical layouts).
   * **Right Pane:** **JEV Verification Inspector & Mentor Console**—displays the NATO Admiralty reliability badge, Anti-Slop score, Lande HVG term hierarchy, Contradiction Alerts, and "Swarm Mentor" approval buttons.
2. **InfoStream / Attack-Index Temporal Ribbon:**
   * Bottom collapsible dock displaying time-series histograms of concept dynamics, wave anomalies, reprint bursts, and narrative intensity curves across selected date windows.
3. **One-Click "Complicate & Deepen" Trigger:**
   * Analysts can right-click any node, edge, or wiki section and select *"Complicate Subgraph"* or *"Verify Contradiction"*, dispatching the OSINT Agent Swarm to hunt for corroborating or refuting primary sources.

---

## 6. Non-Functional Requirements & Guardrails
* **Zero Unverified Hallucination Policy:** If the JEV Verifier calculates an NLI entailment score $< 0.85$ or cannot locate the verbatim substring in the raw archive, the write transaction to KùzuDB is hard-rejected at the type boundary.
* **Anti-AI Slop Quarantine:** Incoming web pages or documents scoring $> 0.65$ on the Synthetic Slop Classifier (low information density, generic LLM transitional phrasing, unattributed claims) are quarantined from knowledge compilation—unless explicitly tagged as an `AdversarialBotArtifact` for disinformation study.
* **Embedded High-Speed Graph Execution:** KùzuDB runs in-process (embedded C++ columnar graph engine) supporting sub-100ms multi-hop Cypher traversals, native vector HNSW indexing, and BM25 full-text search within a single Docker volume.