# ARCHIT.md — System Architecture & Technical Design
**System:** KuzuWiki-OSINT  
**Stack:** Python 3.12 (FastAPI, KùzuDB, Pydantic/Instructor, DeBERTa/GLiNER, LangGraph) + TypeScript / React 19 / Tailwind CSS + Docker Compose  

---

## 1. High-Level Architectural Overview
KuzuWiki-OSINT implements a **Three-Layer Compiled Knowledge Architecture** backed by **KùzuDB** as the unified graph, vector, and full-text storage engine:

1. **Layer 1: Immutable Raw Vault (`/data/raw_vault/` & Object Store):**
   * Stores content-addressed (`SHA-256`) original PDFs, HTML snapshots (WARC/SingleFile), JSON registries, and media transcripts. Never modified by any LLM.
2. **Layer 2: KùzuDB Compiled Graph + Synchronized Wiki (`/data/kuzudb/` & `/data/wiki/`):**
   * **KùzuDB** stores strongly-typed Property Graph tables (`Entity`, `Claim`, `SourceDoc`, `NarrativeWave`, `ComplicationTicket`) with native HNSW vector embeddings and BM25 full-text indexes.
   * **Compiled Wiki Vault (`/data/wiki/*.md`)** mirrors KùzuDB `Entity` and `Concept` syntheses into Git-versioned Markdown files with YAML frontmatter and `[[wikilinks]]`, allowing both programmatic Cypher graph analytics and human/Obsidian inspection.
3. **Layer 3: Domain Schema & JEV Governance (`/config/domain_schemas/`):**
   * Declarative YAML/Pydantic domain packs (`hybrid_warfare.yaml`, `drone_supply_chain.yaml`, `corporate_osint.yaml`) defining allowed entity types, edge topologies, Lande stopword/term filters, and OSINT search templates.

---

## 2. KùzuDB Graph Schema Specification (DDL)
KùzuDB is an embedded, columnar property graph database written in C++ with native Cypher support, strict typing, vector search (`kuzu_vector`), and full-text search (`kuzu_fts`).

```cypher
// =========================================================
// 1. NODE TABLES
// =========================================================

// Immutable Raw Source Document
CREATE NODE TABLE SourceDoc (
    sha256 STRING,
    uri STRING,
    title STRING,
    domain STRING,
    published_at TIMESTAMP,
    ingested_at TIMESTAMP,
    admiralty_reliability STRING,   // A..F
    credibility_rank INT64,         // 1..6
    slop_score DOUBLE,              // 0.0..1.0
    attack_index DOUBLE,            // Lande manipulative intensity score
    raw_archive_path STRING,
    PRIMARY KEY (sha256)
);

// Compiled Domain Entity / Wiki Page Node
CREATE NODE TABLE Entity (
    id STRING,                      // Deterministic slug, e.g., "org:geran-uav-plant-alabuga"
    canonical_name STRING,
    category STRING,                // Person, Organization, MilitarySystem, Component, etc.
    aliases STRING[],
    external_ids MAP(STRING, STRING),
    summary STRING,
    wiki_markdown STRING,           // Full compiled Karpathy Wiki Markdown body
    confidence_score DOUBLE,        // 4-factor confidence + Ebbinghaus decay
    lifecycle_state STRING,         // DRAFT | VERIFIED | DISPUTED | STALE
    hvg_centrality DOUBLE,          // Lande Horizontal Visibility Graph centrality
    embedding DOUBLE[1024],         // BGE-M3 / Text-Embedding-3 vector
    updated_at TIMESTAMP,
    PRIMARY KEY (id)
);

// Atomic Fact / Verifiable Claim Node
CREATE NODE TABLE Claim (
    claim_id STRING,
    statement STRING,
    predicate STRING,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    confidence DOUBLE,
    nli_entailment DOUBLE,
    swarm_votes INT64,
    status STRING,                  // CORROBORATED | SINGLE_SOURCE | CONTRADICTED
    embedding DOUBLE[1024],
    PRIMARY KEY (claim_id)
);

// Lande Term Node (Natural Hierarchy of Terms)
CREATE NODE TABLE DomainTerm (
    term STRING,
    idf_weight DOUBLE,
    hvg_degree INT64,
    burst_score DOUBLE,
    PRIMARY KEY (term)
);

// Autonomous Complication / OSINT Research Ticket
CREATE NODE TABLE ComplicationTicket (
    ticket_id STRING,
    target_entity_id STRING,
    gap_type STRING,                // MISSING_BENEFICIAL_OWNER | UNVERIFIED_CLAIM | CONTRADICTION
    hypothesis_query STRING,
    Generated_dorks STRING[],
    status STRING,                  // OPEN | IN_PROGRESS | RESOLVED | EXHAUSTED
    created_at TIMESTAMP,
    PRIMARY KEY (ticket_id)
);

// =========================================================
// 2. RELATIONSHIP (EDGE) TABLES
// =========================================================

// Typed Domain Relationships between Entities
CREATE REL TABLE RELATES_TO (
    FROM Entity TO Entity,
    relation_type STRING,           // SUPPLIES_COMPONENT, OWNS_CONTROLS, FUNDS, etc.
    weight DOUBLE,                  // Swarm consensus + corroboration weight
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    claim_id STRING,                // Pointer to backing Claim node
    is_disputed BOOLEAN
);

// Verbatim Provenance Grounding (Claim -> SourceDoc)
CREATE REL TABLE EVIDENCED_BY (
    FROM Claim TO SourceDoc,
    exact_quote STRING,
    start_char INT64,
    end_char INT64,
    nli_score DOUBLE,
    extracted_by_swarm_run STRING
);

// Claim Subject/Object Links
CREATE REL TABLE ASSERTS_ABOUT (
    FROM Claim TO Entity,
    role STRING                     // SUBJECT | OBJECT | CONTEXT
);

// Contradiction Edge between Conflicting Claims
CREATE REL TABLE CONTRADICTS (
    FROM Claim TO Claim,
    contradiction_type STRING,      // TEMPORAL | NUMERICAL | FACTUAL_NEGATION
    severity DOUBLE,
    detected_at TIMESTAMP,
    resolution_notes STRING
);

// Media Reprint / Information Cascade Tracking (Lande InfoStream)
CREATE REL TABLE REPRINTS_FROM (
    FROM SourceDoc TO SourceDoc,
    similarity_score DOUBLE,
    lag_seconds INT64
);

// Lande Directed Natural Term Hierarchy
CREATE REL TABLE TERM_DOMINATES (
    FROM DomainTerm TO DomainTerm,
    visibility_weight DOUBLE,
    directional_asymmetry DOUBLE
);
```

---

## 3. Mathematical & Algorithmic Pipeline Details

### 3.1. Prof. Lande’s Horizontal Visibility Graph (HVG) & Term Directionality
Implemented in `backend/app/lande/hvg_network.py`:
1. Given a document segmented into sentences $S = \{s_1, s_2, \dots, s_n\}$ and a sequence of occurrences of term $t$ with local TF-IDF prominence $y(t_a)$ at position $x_a$:
2. Two term occurrences $(x_a, y_a)$ and $(x_b, y_b)$ have **Horizontal Visibility** if every intermediate occurrence $(x_c, y_c)$ with $x_a < x_c < x_b$ satisfies:
   $$y_c < \min(y_a, y_b)$$
3. By aggregating visibility edges across the text corpus, an undirected network $G_{\text{HVG}} = (V, E)$ is formed.
4. **Directionality Resolution (Lande, Dmytrenko, Radziievska Algorithm):** For any connected pair $(t_i, t_j) \in E$, the directed hierarchy $t_i \rightarrow t_j$ ($t_i$ is the broader ontology parent, $t_j$ is the child) is established when the conditional co-occurrence asymmetry satisfies:
   $$P(t_i \mid t_j) > P(t_j \mid t_i) \quad \text{and} \quad k_{\text{out}}(t_i) > k_{\text{out}}(t_j)$$
   These directed edges populate KùzuDB's `TERM_DOMINATES` table and constrain the LLM's ontology classification.

### 3.2. 4-Factor Confidence Scoring & Anti-Slop Math
Every `Entity` and `Claim` in KùzuDB maintains a dynamic confidence score $C \in [0, 1]$:
$$C = \Big(\alpha \cdot S_{\text{corrob}} + \beta \cdot Q_{\text{admiralty}} + \gamma \cdot E_{\text{NLI}} + \delta \cdot K_{\text{swarm}}\Big) \cdot e^{-\lambda \Delta t}$$
Where:
* $S_{\text{corrob}} = 1 - e^{-0.5 \cdot N_{\text{independent}}}$: Independent source count (excluding `REPRINTS_FROM` clones).
* $Q_{\text{admiralty}}$: Normalized Admiralty reliability weight ($A=1.0, B=0.85, C=0.65, D=0.35, E=0.1, F=0.4$).
* $E_{\text{NLI}}$: Cross-encoder entailment score between the `exact_quote` span and the extracted `Claim.statement`.
* $K_{\text{swarm}}$: Agreement ratio across the $N$ virtual experts.
* $e^{-\lambda \Delta t}$: Temporal staleness factor based on domain volatility $\lambda$.

---

## 4. Backend Architecture (Python 3.12 / FastAPI)

### 4.1. Directory Structure
```text
backend/
├── app/
│   ├── main.py                     # FastAPI entry point, lifespan KùzuDB connection pool
│   ├── config.py                   # Pydantic Settings (LLM endpoints, SearXNG, Kuzu paths)
│   ├── db/
│   │   ├── kuzu_client.py          # Thread-safe KùzuDB wrapper, Cypher + Vector + FTS
│   │   ├── schema_init.py          # Idempotent DDL execution & index creation
│   │   └── wiki_sync.py            # Bidirectional sync between KùzuDB Entity & /data/wiki/*.md
│   ├── jev/
│   │   ├── schemas.py              # Strict Pydantic v2 / BAML models
│   │   ├── slop_classifier.py      # Perplexity, burstiness, stylometric & density gate
│   │   ├── nli_verifier.py         # DeBERTa-v3-large NLI & exact substring gate
│   │   └── entity_resolver.py      # Vector + Jaro-Winkler + Deterministic ID deduplication
│   ├── lande/
│   │   ├── hvg_network.py          # Horizontal Visibility Graph & term directionality
│   │   ├── attack_index.py         # Cognitive warfare wave & emotional trigger scoring
│   │   └── reprint_cascade.py      # MinHash shingle deduplication & influence tree
│   ├── agents/
│   │   ├── orchestrator.py         # LangGraph state machine (Ingest -> Compile -> Lint -> Complicate)
│   │   ├── swarm_extractor.py      # Parallel Virtual Expert Swarm execution
│   │   ├── wiki_compiler.py        # Karpathy Markdown compiler & contradiction synthesizer
│   │   ├── linter_agent.py         # Cypher health checks & Ebbinghaus decay
│   │   └── osint_complicator.py    # Deep research agent (SearXNG, OpenCorporates, PDFs)
│   └── api/
│       ├── routes_ingest.py        # Document/URL upload & batch folder watch
│       ├── routes_graph.py         # Cypher subgraph queries, shortest path, Louvain clusters
│       ├── routes_wiki.py          # Compiled wiki CRUD, diff history, --save query filing
│       └── routes_osint.py         # Complication tickets, Attack-Index time series, Swarm Mentor review
├── Dockerfile
└── pyproject.toml
```

### 4.2. Core API Endpoints
* `POST /api/v1/ingest/document` — Uploads PDF/DOCX/URL/Archive; runs `GatekeeperSlopAgent` $\rightarrow$ `LandeNetworkAgent` $\rightarrow$ `JEVSwarmExtractor` $\rightarrow$ `GraphWikiCompilerAgent`.
* `POST /api/v1/query/compiled` — Executes hybrid GraphRAG over KùzuDB compiled Wiki pages (`vector_search` + $k$-hop Cypher expansion). Supports `save_to_wiki: true` to compile the synthesized answer back into KùzuDB.
* `POST /api/v1/osint/complicate/{entity_id}` — Triggers `OSINTComplicatorAgent` to actively search the web, sanctions lists, and registries to deepen the entity’s subgraph.
* `GET /api/v1/analytics/attack-index` — Returns InfoStream/Attack-Index time-series histograms, narrative wave anomalies, and reprint cascades for a given topic or subgraph.
* `GET /api/v1/lint/contradictions` — Returns all active `[:CONTRADICTS]` edges with side-by-side verbatim source quotes for human Swarm Mentor adjudication.

---

## 5. Frontend Architecture (TypeScript, React 19, Tailwind CSS)

### 5.1. Directory Structure
```text
frontend/
├── src/
│   ├── main.tsx
│   ├── types/
│   │   └── jevGraph.ts             # TypeScript interfaces mirroring Python JEV & KùzuDB schemas
│   ├── components/
│   │   ├── layout/
│   │   │   └── WorkbenchShell.tsx  # 3-pane resizable IDE + bottom InfoStream timeline dock
│   │   ├── graph/
│   │   │   ├── KuzuSigmaCanvas.tsx # WebGL Sigma.js / Cosmograph renderer for KùzuDB subgraphs
│   │   │   └── HVG7TermTree.tsx    # Lande Directed Term Hierarchy visualizer
│   │   ├── wiki/
│   │   │   ├── CompiledWikiView.tsx# Markdown renderer with [[Entity]] pills & Admiralty badges
│   │   │   └── VerbatimPopover.tsx # Hover citation inspector showing raw PDF/HTML character span
│   │   ├── osint/
│   │   │   ├── SwarmMentorQueue.tsx# Human-in-the-loop approval for disputed claims & merges
│   │   │   ├── ComplicateModal.tsx # Dispatch & live stream of OSINT Complicator Agent
│   │   │   └── SlopQuarantine.tsx  # Audit log of rejected AI slop & syndicated reprints
│   │   └── analytics/
│   │       └── AttackIndexWave.tsx # Time-series wave anomaly & narrative burst chart
│   ├── hooks/
│   │   └── useKuzuSubgraph.ts      # TanStack Query + WebSocket live graph mutation hook
│   └── services/
│       └── apiClient.ts
├── tailwind.config.ts
├── package.json
└── Dockerfile
```

---

## 6. Dockerization & Deployment (`docker-compose.yml`)

The entire system is containerized for reproducible local or air-gapped/VPC OSINT deployment, bundling the React UI, FastAPI + KùzuDB backend, Redis task queue, SearXNG metasearch engine for autonomous OSINT complication, and local embedding/NLI inference.

```yaml
version: "3.9"

services:
  # 1. Python Backend + Embedded KùzuDB + JEV Classifiers
  kuzuwiki-backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: kuzuwiki-backend
    restart: unless-stopped
    environment:
      - KUZU_DB_PATH=/data/kuzudb
      - WIKI_VAULT_PATH=/data/wiki
      - RAW_VAULT_PATH=/data/raw_vault
      - REDIS_URL=redis://redis:6379/0
      - SEARXNG_URL=http://searxng:8080
      - LLM_API_BASE=${LLM_API_BASE:-http://host.docker.internal:11434/v1}
      - LLM_API_KEY=${LLM_API_KEY}
      - JEV_NLI_MODEL=MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli
      - JEV_EMBEDDING_MODEL=BAAI/bge-m3
    volumes:
      - kuzu_data:/data/kuzudb
      - wiki_vault:/data/wiki
      - raw_vault:/data/raw_vault
      - ./config/domain_schemas:/app/config/domain_schemas:ro
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - searxng

  # 2. Autonomous Background Worker (Compile, Lint, OSINT Complicator Loop)
  kuzuwiki-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: kuzuwiki-worker
    command: celery -A app.agents.worker worker --beat --loglevel=info --concurrency=2
    restart: unless-stopped
    environment:
      - KUZU_DB_PATH=/data/kuzudb
      - WIKI_VAULT_PATH=/data/wiki
      - RAW_VAULT_PATH=/data/raw_vault
      - REDIS_URL=redis://redis:6379/0
      - SEARXNG_URL=http://searxng:8080
      - LLM_API_BASE=${LLM_API_BASE:-http://host.docker.internal:11434/v1}
      - LLM_API_KEY=${LLM_API_KEY}
    volumes:
      - kuzu_data:/data/kuzudb
      - wiki_vault:/data/wiki
      - raw_vault:/data/raw_vault
      - ./config/domain_schemas:/app/config/domain_schemas:ro
    depends_on:
      - kuzuwiki-backend
      - redis

  # 3. TypeScript + React + Tailwind OSINT Workbench UI
  kuzuwiki-frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: kuzuwiki-frontend
    restart: unless-stopped
    environment:
      - VITE_API_BASE_URL=http://localhost:8000/api/v1
      - VITE_WS_URL=ws://localhost:8000/ws
    ports:
      - "3000:80"
    depends_on:
      - kuzuwiki-backend

  # 4. Private SearXNG Instance for Autonomous OSINT Web Complication
  searxng:
    image: searxng/searxng:latest
    container_name: kuzuwiki-searxng
    restart: unless-stopped
    volumes:
      - ./config/searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://searxng:8080/
    ports:
      - "8088:8080"

  # 5. Redis Broker for Swarm Task Queue & WebSocket Pub/Sub
  redis:
    image: redis:7.4-alpine
    container_name: kuzuwiki-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data

volumes:
  kuzu_data:
  wiki_vault:
  raw_vault:
  redis_data:
```

---

## 7. Concurrency & KùzuDB Read/Write Pattern
Because **KùzuDB** is an embedded database that supports **multiple concurrent `READ_ONLY` connections or a single `READ_WRITE` connection** per database directory:
* The **FastAPI process (`kuzuwiki-backend`)** owns the single `READ_WRITE` KùzuDB connection pool via an asynchronous write-queue actor (`asyncio.Queue`) that serializes graph mutations (`MERGE` nodes/edges) in sub-millisecond batches while serving concurrent Cypher read queries.
* The **Background Worker (`kuzuwiki-worker`)** performs heavy CPU/GPU tasks (PDF OCR, Lande HVG computation, JEV Swarm LLM calls, DeBERTa NLI verification, SearXNG scraping) and commits validated `JEVDistillationBundle` payloads to the backend's internal `/internal/v1/kuzu/commit` endpoint, preventing file-lock contention on `/data/kuzudb`.
---

## 12. As-Built Status (what the code actually does)

This section records the **as-built** reality, which differs from the design
above in a handful of deliberate ways. The design documents remain the target;
this is the current state.

### 12.1 Corrections to the design

| Design assumption | As-built | Why |
| :--- | :--- | :--- |
| `kuzudb` Python package, `KuzuDB.get_instance()`, `cypher_query()`, `commit()` | `kuzu` ≥ 0.11, `kuzu.Database(path)`, `kuzu.Connection(db)`, `conn.execute(query, params)` | `kuzudb` does not exist on PyPI; the previously used API was fictional. |
| Scalar `CREATE INDEX ... USING HNSW` | `CALL create_vector_index(table, idx, column)` / `CALL create_fts_index(table, idx, cols)` | Kùzu 0.11 has no standalone `CREATE INDEX`. The FTS index *is* real BM25 (`query_fts_index`). |
| `shortestPath()`, `algo.louvain.stream`, `LIMIT` inside `CALL {}` | BFS over the neighbourhood; connected components; `LIMIT` only at query level | None of those Neo4j constructs exist in the Kùzu dialect. |
| `KUZU_DB_PATH=/data/kuzudb` | `KUZU_DB_PATH=/data/kuzudb/graph.kuzu` | Kùzu refuses to open a **directory**; the path must name a file. |
| `asyncio.Queue` write actor with fire-and-forget writes | single dedicated executor thread; every write is awaited | Unawaited writes were silently dropped. |
| NLI gate scoring the quote against the entity names | deterministic lexical entailment over statement-vs-quote, behind a pluggable `NLIClient` | The old scorer returned 0.0 for every realistic quote, rejecting 100% of relations. The DeBERTa backend can be dropped in behind the same interface. |
| Docker: `pip install -e .` before copying sources; `.env` baked in; `npm ci` without a lockfile | sources copied first; `.env` excluded by `.dockerignore`; `npm install` fallback | The image "built green" while installing nothing, and leaked the live API key into a layer. |

### 12.2 Implemented end-to-end

* **Ingest → compile → dossier**: document → SHA-256 archive → slop score →
  Admiralty grade → Lande HVG → three-expert swarm → weighted consensus →
  entailment gate → KùzuDB upsert (`Entity`, `Claim`, `DomainTerm`,
  `SourceDoc`) with `EVIDENCED_BY` provenance edges → Git-versioned Markdown
  dossier with YAML frontmatter and `[[wikilinks]]`.
* **Reprint cascade**: MinHash shingles over the archived text, `REPRINTS_FROM`
  edges with the publication lag, and no corroboration credit for reprints.
* **Adversarial lint**: contradiction detection (writing `[:CONTRADICTS]`
  edges), persisted Ebbinghaus decay, Attack-Index wave anomalies, and
  `ComplicationTicket`s for structural gaps.

### 12.3 Specified but not implemented

* `POST /api/v1/query/compiled` — hybrid GraphRAG over the compiled graph.
* `WS /ws` — live graph mutation stream (the frontend hook degrades to a
  no-op and reports `connected: false`).
* Celery worker (`backend/app/agents/worker.py`) and beat schedule.
* SearXNG deployment (the agent can use an external instance via
  `SEARXNG_URL`, but no configuration ships with the repo).
* Entity embeddings (the `Entity.embedding` column and its HNSW index exist;
  nothing writes vectors yet, so the vector path of entity resolution is
  inert until an embedding model is configured).
* `DerivedSynthesis` filing from analyst queries is stored, but the
  `PUT /api/v1/wiki/{slug}` route returns a payload the frontend does not yet
  send as JSON.

### 12.4 Package layout

The Python package is `backend/kuzuwiki/` (imported as `kuzuwiki.*`), not
`backend/app/`. `app` was a namespace package and could be shadowed by an
unrelated `app` package elsewhere on `sys.path`.
