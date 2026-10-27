# KuzuWiki-OSINT Project

Graph-Compiled Expert Intelligence & Anti-Slop Knowledge System

## Overview

KuzuWiki-OSINT adapts the LLM Wiki compilation pattern and replaces flat Markdown-only link structures with an embedded, high-performance **KùzuDB** property graph + vector + full-text engine. Anchored in Prof. Dmytro Lande's frameworks (Horizontal Visibility Graphs, Swarm of Virtual Experts, Attack-Index wave detection), the system acts as a living **Domain Expert System** that continuously complicates, deepens, and verifies its own knowledge graph.

## System Architecture

**Three-Layer Compiled Knowledge Architecture**:

1. **Layer 1: Immutable Raw Vault** (`/data/raw_vault/` & Object Store)
   - Stores content-addressed (`SHA-256`) original PDFs, HTML snapshots, JSON registries, and media transcripts
   - Never modified by any LLM

2. **Layer 2: KùzuDB Compiled Graph + Synchronized Wiki** (`/data/kuzudb/` & `/data/wiki/`)
   - **KùzuDB** stores strongly-typed Property Graph tables (`Entity`, `Claim`, `SourceDoc`, `NarrativeWave`, `ComplicationTicket`)
   - **Compiled Wiki Vault** mirrors KùzuDB `Entity` and `Concept` syntheses into Git-versioned Markdown with YAML frontmatter and `[[wikilinks]]`

3. **Layer 3: Domain Schema & JEV Governance** (`/config/domain_schemas/`)
   - Declarative YAML/Pydantic domain packs defining entity types, edge topologies, Lande term filters, and OSINT search templates

## Core Features

### Four-Phase Knowledge Compilation Lifecycle

1. **INGEST**: Raw PDFs, OSINT scrapes, corporate registries, and Telegram/web dumps are hashed (`SHA-256`), archived immutably, and passed through the **Anti-Slop & JEV Classifier Gate**

2. **COMPILE**: Validated atomic claims, typed entities, and directed relationships are upserted into **KùzuDB**. Corresponding structured Markdown wiki pages are incrementally compiled and updated.

3. **QUERY & COMPOUND**: Analysts query the compiled KùzuDB graph + wiki articles using hybrid Cypher traversal + Vector + BM25 search. High-value analytical answers are **filed back (`--save`)** into the graph as `DerivedSynthesis` nodes.

4. **LINT & AUTONOMOUS COMPLICATION**: Background agents scan KùzuDB for structural orphans, temporal decay, conflicting claims, and low-density subgraphs. They formulate targeted OSINT queries, search the deep/surface web, and ingest new verified evidence.

### Type-Safe JEV (Joint Extraction & Verification) Classifiers

Every document distillation and graph mutation is governed by **Type-Safe JEV Models**:
- **Strict Schema Enforcement**: Python `Pydantic v2` + `Instructor` / `BAML` + local DeBERTa/GLiNER cross-encoders
- **Three-Stage JEV Pipeline**:
  1. **J — Joint Entity & Relation Extraction**
  2. **E — Epistemic & Slop Classification**
  3. **V — Verbatim Grounding & Entailment Verification**

### Theoretical Foundation (Prof. Dmytro Lande Framework)

1. **Horizontal Visibility Graphs (HVG) & Natural Term Hierarchies**
2. **Swarm of Virtual Experts (Consensus Semantic Networking)**
3. **Attack-Index & Information Flow Lifecycle Dynamics**
4. **Strict Verbatim Provenance (InfoStream RAG Standard)**

## Target Use Cases & Domain Profiles

| Domain Focus | Primary Entities | Key JEV Relations | Analytical Output |
| :--- | :--- | :--- | :--- |
| **Hybrid & Cognitive Warfare** | `NarrativeFrame`, `MediaOutlet`, `BotNetwork`, `GeopoliticalEvent`, `Actor` | `AMPLIFIES`, `REPRINTS_FROM`, `EXPLOITS_BIAS`, `ATTRIBUTED_TO` | Attack-Index wave charts, narrative mutation trees, zero-patient source identification |
| **Drone Industry & Supply Chains** | `UAVModel`, `SubComponent`, `Manufacturer`, `Distributor`, `CustomsHSCode` | `CONTAINS_PART`, `MANUFACTURED_BY`, `TRANSITED_THROUGH`, `SANCTIONED_BY` | Multi-hop sanction evasion paths, chokepoint centrality analysis, BOM wiki dossiers |
| **Political Influence & Lobbying** | `Politician`, `ThinkTank`, `Donor`, `Legislation`, `Foundation` | `FUNDS`, `CO_AUTHORS`, `BOARD_MEMBER_OF`, `LOBBIES_FOR` | Hidden influence pathfinding, temporal alignment of donations vs. legislative voting |
| **Corporate OSINT & Malactivity** | `Company`, `BeneficialOwner`, `OffshoreEntity`, `Litigation`, `WalletAddress` | `OWNS_SHARE`, `SHARES_DIRECTOR_WITH`, `REGISTERED_AT`, `TRANSACTED_WITH` | Shell company cluster detection, beneficial ownership unrolling, red-flag audit reports |

## Technical Stack

**Backend (Python 3.12 / FastAPI):**
- KùzuDB (embedded columnar graph engine)
- Pydantic v2 / Instructor / BAML
- OpenRouter API integration (Nemotron, Flint Gemma, MiniMax)
- DeBERTa-v3-large-mnli-fever-anli-ling-wanli
- BGE-M3 embedding model
- Celery + Redis task queue
- LangGraph / AgentFlow orchestrator

**Frontend (TypeScript / React 19 / Tailwind CSS):**
- Obsidian-like wiki IDE with 3-pane layout
- Sigma.js / Cosmograph WebGL graph canvas
- Lande directed term hierarchy visualizer
- Real-time WebSocket graph updates
- JEV verification inspector

**Infrastructure:**
- Docker Compose (5 services)
- SearXNG metasearch engine
- Sandboxed web scraping
- Local embedding/NLI inference

## API Endpoints

All routes are served by the FastAPI backend on port `8000`. The set below is
the **as-built** contract; `GET /openapi.json` is always authoritative.

### Ingest
- `POST /api/v1/ingest/document` — Upload PDF/DOCX/TXT/HTML or fetch a URL; runs
  Gatekeeper → Lande HVG → JEV Swarm → Graph-Wiki Compiler
- `GET /api/v1/ingest/documents` — Index of the immutable raw vault

### Graph
- `GET /api/v1/graph/entities` — Compiled entity list (ontology picker)
- `GET /api/v1/graph/entities/count` — Compiled entity count
- `GET /api/v1/graph/entity/{entity_id}` — One entity with its relations
- `POST /api/v1/graph/subgraph` — k-hop neighbourhood for the graph canvas
- `POST /api/v1/graph/shortest-path` — Bounded shortest path between two entities
- `POST /api/v1/graph/clusters` — Connected communities of the relation graph
- `GET /api/v1/graph/terms` — The Lande term hierarchy (`DomainTerm` + `TERM_DOMINATES`)

### Wiki
- `GET /api/v1/wiki/{slug}` — A compiled dossier by slug
- `GET /api/v1/wiki/entity/{entity_id}` — The dossier of an entity, resolved via its slug
- `PUT /api/v1/wiki/{slug}` — File an analyst synthesis into the vault (and the graph)

### OSINT & Lint
- `POST /api/v1/osint/complicate/{entity_id}` — Dispatch the OSINT Complicator Agent
- `GET /api/v1/osint/attack-index` — InfoStream / Attack-Index time series
- `GET /api/v1/osint/lint/contradictions` — Contradiction, decay, wave and gap report
- `GET /api/v1/osint/tickets` — Open OSINT complication tickets
- `POST /api/v1/osint/tickets/review` — Swarm Mentor decision (approve/reject/defer)

### System
- `GET /health` — Liveness probe

**Not yet implemented** (specified in `PRD.md`, see `ARCHIT.md` §12):
`POST /api/v1/query/compiled` (hybrid GraphRAG) and the `WS /ws` live-graph
WebSocket endpoint.

## User Interface

The frontend is an analyst-grade workbench combining:

1. **Tri-Pane Knowledge Workbench:**
   - Left Pane: Domain Ontology Tree, Immutable Source Vault, Live Autonomous Agent Queue
   - Center Pane: Synchronized Dual-View (Compiled Wiki Article + Interactive KùzuDB Graph Canvas)
   - Right Pane: JEV Verification Inspector & Mentor Console

2. **InfoStream / Attack-Index Temporal Ribbon**
   - Bottom collapsible dock displaying time-series histograms

3. **One-Click "Complicate & Deepen" Trigger**
   - Right-click any node, edge, or wiki section to dispatch OSINT agents

## Zero Unverified Hallucination Policy

If the JEV Verifier calculates an NLI entailment score < 0.85 or cannot locate the verbatim substring in the raw archive, the write transaction to KùzuDB is hard-rejected at the type boundary.

## Anti-AI Slop Quarantine

Incoming web pages or documents scoring > 0.65 on the Synthetic Slop Classifier (low information density, generic LLM transitional phrasing, unattributed claims) are quarantined from knowledge compilation — unless explicitly tagged as an `AdversarialBotArtifact` for disinformation study.

## Embedded High-Speed Graph Execution

KùzuDB runs in-process supporting sub-100ms multi-hop Cypher traversals, native vector HNSW indexing, and BM25 full-text search within a single Docker volume.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/asiaat/graph_wiki.git
cd graph_wiki

# Install dependencies
pip install -e backend

# Configure the environment
cp backend/.env.example backend/.env
# set OPENROUTER_API_KEY, then adjust the local paths:
#   KUZU_DB_PATH=./data/kuzudb/graph.kuzu   (KùzuDB needs a FILE path)
#   WIKI_VAULT_PATH=./data/wiki
#   RAW_VAULT_PATH=./data/raw_vault

# Start the stack (backend + workbench UI)
docker compose up --build

# Access the workbench at http://localhost:3000
```

### Running the backend directly

```bash
cd backend
uvicorn kuzuwiki.main:app --reload --port 8000
```

### Running the frontend directly

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173, proxies /api to :8000
```

### Tests

```bash
cd backend && python -m pytest     # 90+ tests, no API key required
cd frontend && npm run typecheck
```

The backend test suite mocks the LLM, so it runs fully offline and
deterministically. The KùzuDB layer, the entailment gate, the domain packs and
the API contract are all covered.

## Key Features

- **Zero unverified hallucination** — NLI + verbatim gating
- **Anti-AI slop quarantine** — Stylometric and density classification
- **Autonomous self-complication** — OSINT agent swarm with deep web research
- **Domain-specific JEV models** — Type-safe extraction and verification
- **Graph-wiki sync** — Dual programmatic + human-readable knowledge
- **Conflict detection & resolution** — Cognitive warfare wave monitoring

## Architecture Diagram

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
               | Linter & Attack- |---------->| cator & Deep     |
               | Index Agent       |  Spawns   | Research Agent    |
               +-------------------+  Tickets  +-------------------+
```

## Contributing

This repository implements a comprehensive OSINT system for hybrid warfare analysis, supply chain tracking, political influence, and corporate malactivity. All development follows Prof. Dmytro Lande's theoretical frameworks and maintains strict verification standards.

For contribution guidelines, please refer to the project's contribution documentation.

---

**License:** Proprietary for KuzuWiki-OSINT development
**Contact:** for access to the full repository and API documentation