# DocAgent Complete Rebuild Design

## Context

The current codebase is in an intermediate state:

- the backend already has a newer `app/` shell for services, schemas, and infra
- the core ingest, retrieval, and parsing logic still depends heavily on `backend/utils/*`
- LLM usage is mostly limited to topic naming and reranking instead of being a first-class part of the main document lifecycle
- block indexing capability is still inconsistent across formats, especially for Excel and PPT
- frontend capabilities are centered on upload, document list, search, and preview, but do not yet provide document QA or graph-style exploration

The target product is no longer a generic “document classifier.” It becomes a local-first AI document knowledge base for individual researchers and small collaborative teams that manage mixed office files and need semantic retrieval, cross-document QA, and automatic structuring.

This design defines the full end-state rebuild and the migration path needed to replace the remaining old core.

## Product Positioning

### Users

Primary users:

- graduate students and researchers
- small research groups
- small operational teams that share reports, meeting notes, proposals, papers, and attachments

### Core Problems

The product must solve four daily problems:

1. locating a remembered document when the filename or folder is forgotten
2. finding which documents mention a person, concept, organization, or time
3. comparing how multiple documents discuss the same topic
4. auto-organizing an unmanaged folder of mixed documents into useful categories

### Product Statement

The system is a local-first AI document knowledge base with:

- multi-format ingest
- semantic and keyword retrieval
- document-grounded question answering
- automatic classification and summarization
- lightweight entity graph exploration

This is intentionally positioned between a personal knowledge base and a lightweight team document assistant. It is not a full enterprise governance system, workflow engine, or SaaS collaboration suite.

## Goals

1. Make LLMs a first-class component in every core chain: ingest, retrieval, QA, summarization, and classification.
2. Replace the remaining `backend/utils/*` core with a new `backend/app/domain/*` architecture.
3. Standardize multi-format parsing and block extraction so PDF, DOCX, XLSX, PPTX, EML, TXT, images, and OCR flows fit the same ingest contract.
4. Add real user-facing capabilities that demonstrate model value:
   - query understanding
   - cross-document QA
   - structured summaries
   - entity graph exploration
5. Keep the implementation practical for a local demo environment:
   - FastAPI
   - Vue 3
   - SQLite
   - Chroma
   - local filesystem
6. Preserve phased delivery so the system can remain runnable during the rebuild.

## Non-Goals

1. Introducing multi-tenant SaaS deployment, online collaboration editing, or cloud synchronization.
2. Introducing a heavy graph database such as Neo4j in phase one of the rebuild.
3. Building a full workflow engine, approval center, or enterprise RBAC platform.
4. Making OCR, multimodal reasoning, or Excel agentic execution perfect on the first pass.
5. Preserving the old `utils` internals indefinitely. Compatibility shims may exist temporarily, but the target core is `app/domain`.

## Design Principles

### LLM As System Backbone

The LLM must not be an optional decoration after retrieval. It must participate in:

- document understanding during ingest
- query analysis before recall
- ranking or arbitration after hybrid recall
- answer generation with citations
- structured summaries and graph extraction

### Replace Shell-Over-Legacy

The new `app/services` and `app/infra` layers must stop delegating core behavior into ad hoc utilities. The rebuild must pull parsing, chunking, indexing, retrieval logic, and LLM orchestration into explicit domain modules with stable interfaces.

### Document-Centric Over Chunk-Centric

Blocks remain the atomic evidence unit, but every feature must return document-grounded results and preserve document context such as heading path, page, slide, sheet, or source section.

### Local-First Pragmatism

The system should run on a local workstation without requiring distributed infrastructure. Network-dependent LLM providers remain supported, but the storage and retrieval system stays local by default.

## Six LLM Core Chains

The rebuild makes LLM participation mandatory in six core chains. This is the defining product and architecture decision of the redesign.

### 1. Ingest-Time Structured Extraction

For each document, the LLM extracts structured metadata rather than only generating an embedding.

Required outputs:

- `doc_type`
- `summary`
- `key_entities`
- `key_concepts`
- `time_mentions`
- `action_items`
- `questions_answered`

These fields are persisted to SQLite and become first-class retrieval and filtering signals.

### 2. Query Understanding And Rewrite

Before retrieval, the LLM converts the user query into a structured retrieval plan.

Required outputs:

- `intent`
- `expanded_queries`
- `entity_filters`
- `time_filter`
- `doc_type_hint`

This output drives multi-route recall rather than only a single embedding lookup.

### 3. Retrieval-Backed QA

After recall, the system supports document-grounded QA over selected or global document sets.

Required behavior:

- retrieve relevant blocks
- build structured context
- stream answer generation
- attach citations to document or block anchors

This is the main feature that upgrades the system from search tool to document assistant.

### 4. Dual-Path Classification And Arbitration

Classification is no longer “cluster first, LLM name later.”

Required behavior:

- embedding clustering produces candidate topic signal
- LLM zero-shot classification produces candidate semantic label
- LLM arbitrates both signals into final topic, confidence, and explanation

### 5. Multi-Level Summarization

The system must provide:

- single-document executive summary
- single-document detailed summary
- cross-document synthesis
- incremental relatedness judgment for new documents against existing documents

### 6. Lightweight Graph Extraction

For each document, the LLM extracts entity-relation triples.

Required behavior:

- persist triples
- support graph view payload generation
- combine graph evidence with retrieval signals when useful

This is a lightweight GraphRAG layer intended for exploration and retrieval assistance, not a full standalone graph platform.

## Target Architecture

```text
Frontend (Vue 3)
  Upload / Documents / Search / QA / Graph / Admin
            |
        HTTP / SSE / WebSocket
            |
API Layer (FastAPI /api/v2)
  documents / retrieval / qa / topics / pipeline / admin
            |
Application Services
  IngestPipeline / RetrievalService / QAService / TopicService / SummaryService / ExportService
            |
Domain Layer
  extraction / chunking / indexing / retrieval / llm
            |
Infrastructure Layer
  metadata_store / vector_store / graph_store / embedding_provider / cache / file_store
            |
Persistence
  SQLite / Chroma / filesystem / JSON graph artifacts
```

The system is organized into four layers with strict responsibilities:

1. API layer validates inputs, resolves dependencies, and formats responses.
2. Application services orchestrate workflows and cross-domain operations.
3. Domain modules implement the core document intelligence logic.
4. Infrastructure modules provide storage, embedding, caching, and provider adapters.

## Backend Directory Structure

The target backend structure is:

```text
backend/
├── main.py
├── config.py
├── api/
│   ├── deps.py
│   └── v2/
│       ├── documents.py
│       ├── retrieval.py
│       ├── qa.py
│       ├── topics.py
│       ├── pipeline.py
│       └── admin.py
├── app/
│   ├── schemas/
│   │   ├── document.py
│   │   ├── retrieval.py
│   │   ├── qa.py
│   │   └── topic.py
│   ├── services/
│   │   ├── ingest_pipeline.py
│   │   ├── retrieval_service.py
│   │   ├── qa_service.py
│   │   ├── topic_service.py
│   │   ├── summary_service.py
│   │   └── export_service.py
│   ├── domain/
│   │   ├── extraction/
│   │   ├── chunking/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   └── llm/
│   └── infra/
│       ├── metadata_store.py
│       ├── vector_store.py
│       ├── graph_store.py
│       ├── embedding_provider.py
│       ├── cache.py
│       └── file_store.py
└── alembic/
```

This structure intentionally supersedes legacy `backend/utils/*` logic. Existing utility modules may be wrapped temporarily while migration is in progress, but no new feature should be built directly on those legacy modules.

## API Design

### Versioning

All new functionality is exposed under `/api/v2`. Existing `/api/*` routes may continue to run during migration, but the rebuild targets `v2` as the canonical contract.

### Route Groups

#### `documents`

Responsibilities:

- upload and ingest documents
- list and filter documents
- delete documents
- preview and detail retrieval
- show ingest status and structured metadata

#### `retrieval`

Responsibilities:

- smart document search
- block search
- query analysis feedback
- similar-document lookup

#### `qa`

Responsibilities:

- cross-document question answering
- streaming answer generation with citations
- QA session history

#### `topics`

Responsibilities:

- topic assignment results
- topic tree browsing
- graph view payloads
- classification feedback submission

#### `pipeline`

Responsibilities:

- rebuild indices
- retry failed ingest jobs
- re-run summarization or classification

#### `admin`

Responsibilities:

- system health
- embedding model metadata
- token usage statistics
- cache and provider status

## Core Domain Contracts

### Document Representation

Each document has three layers of representation:

1. raw file and parser output
2. normalized blocks and structural metadata
3. LLM-enriched semantic metadata

The normalized document object must preserve:

- document identity
- mime type and canonical file family
- text and structural segments
- pages, slides, sheets, or sections when applicable
- source parser details

### Block Contract

Every extracted block must support a unified minimum schema:

- `block_id`
- `doc_id`
- `block_type`
- `text`
- `order_index`
- `page_number` nullable
- `sheet_name` nullable
- `slide_number` nullable
- `heading_path`
- `source_locator`
- `metadata`

Format-specific extractors may attach richer metadata, but all downstream components depend on this base contract.

### LLM Metadata Contract

Each ingested document receives LLM-enriched metadata including:

- `llm_doc_type`
- `llm_summary`
- `llm_detailed_summary`
- `key_entities`
- `key_concepts`
- `time_mentions`
- `action_items`
- `questions_answered`
- `related_docs`
- `duplicate_of` nullable

These fields are stored explicitly instead of being implicit in prompts or cached ad hoc.

### Prompt Ownership And Output Stability

Structured LLM tasks must return schema-bound JSON or equivalent validated payloads. Free-form prose is acceptable for summaries and QA output, but extraction, query analysis, classification, and triple extraction must have schema validation and repair paths.

## Extraction Architecture

The extraction subsystem moves into `backend/app/domain/extraction/`.

### Dispatcher

`dispatcher.py` selects the appropriate extractor by MIME type and extension, not by route-level branching.

### Extractors

Required extractors:

- `pdf.py`
- `docx.py`
- `excel.py`
- `pptx.py`
- `email.py`
- `image_ocr.py`
- optional shared plain text extractor for `.txt` and similar files

### Format Handling Rules

#### PDF

- use structure-aware parsing first
- allow OCR fallback for scanned content
- preserve page numbers and heading or layout boundaries when available

#### DOCX

- preserve heading hierarchy, paragraphs, lists, and tables
- retain logical ordering

#### XLSX

- support block extraction by sheet
- capture sheet names, header rows, and table-like ranges
- represent each sheet or table region as a block sequence instead of flattening the workbook into one blob

#### PPTX

- support block extraction by slide
- capture slide number, title, and text boxes
- preserve per-slide segmentation for retrieval and QA citation

#### EML and Images

- email parsing should extract headers, subject, sender, recipients, body, and attachments metadata
- image flow should go through OCR and produce page-like text blocks

This directly fixes the current inconsistency where extraction works for more formats than block indexing.

## Chunking Architecture

Chunking moves into `backend/app/domain/chunking/` and becomes strategy-based.

### Strategies

Required strategies:

- `structural.py`
- `semantic.py`
- `sliding.py`

### Strategy Selection Rules

- PDF and DOCX default to structural chunking
- Excel and PPTX use structure-derived blocks and may bypass additional chunking unless a secondary split is needed
- semantic chunking is available for long unstructured text where structural markers are weak
- sliding window is the fallback when no reliable structure exists

The chunking layer must return stable, deterministic block order and identifiers so document anchors remain usable after re-indexing within the same version.

## Indexing Architecture

Indexing moves into `backend/app/domain/indexing/`.

### Vector Index

`vector_index.py` wraps Chroma and stores block embeddings plus sufficient metadata for citation and document regrouping.

### BM25 Index

`bm25_index.py` manages sparse lexical retrieval with persistent storage and rebuild support.

### Graph Index

`graph_index.py` provides a lightweight entity-relationship retrieval layer backed by JSON artifacts and SQLite triples, not a dedicated graph database.

### Indexing Rules

Each ingested document must update:

- vector index
- BM25 index
- document metadata store
- entity index
- graph triples store when available

The indexing system must support:

- upsert by document
- delete by document
- rebuild by collection
- status tracking

## Retrieval Architecture

Retrieval moves into `backend/app/domain/retrieval/` and `backend/app/services/retrieval_service.py`.

### Query Analysis

Before recall, the LLM analyzes the user query into a structured plan:

- intent
- expanded queries
- entity filters
- time filter
- doc type hints

This allows the system to distinguish:

- factual lookup
- document location
- summary
- comparison

This module is responsible for query rewrite and intent understanding, not the retriever itself. It should be implemented as a dedicated domain component instead of prompt logic embedded inside the retrieval service.

### Multi-Route Recall

The retrieval service performs three recall paths in parallel:

1. vector retrieval using expanded queries
2. BM25 retrieval using the original query and optionally expanded variants
3. graph retrieval using extracted entities or concept hints

### Fusion

Results are merged with reciprocal rank fusion rather than a fixed alpha blend. This is more robust across heterogeneous recall channels and avoids tightly coupled per-score calibration.

### Reranking

For smart mode, the top fused candidates are reranked by:

- LLM reranking by default
- optional cross-encoder reranking if available locally

### Document-Centric Output

The final output is regrouped into a document-centered response that includes:

- document-level score
- matched blocks
- reason hints
- surfaced entities and summary snippets

The result payload must support both document list display and downstream QA context construction.

For smart search mode, the query analysis payload should also be returned to the frontend so the user can see and optionally edit the interpreted intent and expanded terms.

## Ingest Pipeline

`backend/app/services/ingest_pipeline.py` becomes the canonical ingest orchestrator.

### Required Pipeline Stages

1. file registration and status initialization
2. text and structure extraction
3. LLM metadata extraction
4. entity extraction
5. knowledge-graph triple extraction
6. chunking or normalized block generation
7. vector and BM25 indexing
8. topic assignment
9. similar-document detection
10. final status transition to ready

### Failure Model

Every stage must persist status so that failed documents can be retried without re-uploading the file. Failures should be observable at the document level, not only in logs.

### LLM Participation During Ingest

The LLM is used to derive structured metadata from the document content, including:

- document type
- summary
- concepts
- entities
- time expressions
- action items
- knowledge-graph triples

These outputs must be normalized and stored, not only rendered in a response.

The ingest pipeline should run summary extraction, entity extraction, and triple extraction concurrently where possible, and should tolerate partial model-task failure by marking the specific sub-stage rather than failing the entire document unconditionally.

### Topic Assignment

Topic assignment uses dual-path classification:

1. cluster-based candidate topic
2. LLM zero-shot classification

The LLM then arbitrates between both signals and returns:

- final label
- confidence
- explanation

This replaces the current pattern where LLM usage is mostly limited to naming clusters.

## QA Architecture

`backend/app/services/qa_service.py` provides document-grounded QA.

### Scope

The QA service must support:

- selected-document QA
- whole-library QA
- streaming answers
- citation tracking

### Flow

1. run focused block retrieval for the question
2. construct structured RAG context from retrieved blocks
3. stream answer tokens through the LLM gateway
4. parse or map citations back to document and block identifiers
5. persist the QA session

### Citation Requirements

Each answer must be traceable to source evidence. The frontend should be able to display citation chips such as a document name, page, section, or slide and navigate back to the source.

### Output Style

The QA output should support:

- direct answer
- comparative answer across multiple documents
- answer with uncertainty when evidence is weak

The service must prefer refusal or qualified answers over unsupported synthesis.

## Summarization Architecture

`backend/app/services/summary_service.py` provides two summary levels:

1. per-document summary
2. cross-document synthesis

### Per-Document Summary

Required outputs:

- short executive summary
- detailed summary

### Cross-Document Summary

The service must be able to summarize:

- selected search results
- selected documents
- topic-scoped document sets

The cross-document summary path must be citation-aware so that summaries remain grounded in source blocks.

## Topic And Graph Architecture

`backend/app/services/topic_service.py` becomes the single entry point for topic management, classification feedback, and graph-facing aggregations.

### Topic Responsibilities

- assign topics during ingest
- expose topic tree and topic-group views
- accept user corrections
- feed few-shot examples back into future classification prompts

`TopicService` is the consolidation point for responsibilities that are currently split across topic tree, clustering, and labeler services.

### Classification Feedback

When a user corrects a topic label, the system stores the correction and can use it as a few-shot example in later classification tasks. This creates an incremental improvement loop without requiring online model training.

### Knowledge Graph

The graph subsystem extracts triples of:

- subject
- predicate
- object

Triples are stored in SQLite and optionally serialized as JSON graph artifacts for fast graph view loading.

The graph is intentionally lightweight:

- storage: SQLite + JSON
- in-memory processing: NetworkX or equivalent lightweight library
- frontend payload: node-edge graph for interactive browsing

This is a simplified GraphRAG layer, not a full graph database platform.

## LLM Gateway

All model access must pass through `backend/app/domain/llm/gateway.py`.

### Responsibilities

- provider abstraction
- retries with backoff
- fallback routing
- semantic or keyed caching where safe
- token usage tracking
- streaming response support

### Providers

The gateway must support at least:

- Doubao
- OpenAI-compatible provider interface
- optional local fallback such as Ollama

### Task-Aware Routing

The gateway selects model settings per task category:

- extract
- classify
- rerank
- summarize
- QA

This keeps cost, latency, and output quality controllable.

### Prompt Ownership

All prompts move into `backend/app/domain/llm/prompts.py` so they are versioned, reviewable, and reusable instead of being scattered across utility modules.

## Data Model Changes

The rebuild retains the existing documents metadata concept but extends the schema to persist LLM outputs, entities, QA history, and graph triples.

### `documents`

Required new fields:

- `llm_doc_type`
- `llm_summary`
- `llm_detailed_summary`
- `duplicate_of`
- `related_docs`
- `ingest_status`

### `doc_entities`

Purpose:

- entity-based filtering
- search boosts
- graph support

Minimum fields:

- `id`
- `doc_id`
- `entity_text`
- `entity_type`
- `context`
- `created_at`

Indexes:

- entity text
- doc id

### `qa_sessions`

Purpose:

- QA history
- session playback
- answer and citation persistence

Minimum fields:

- `id`
- `query`
- `doc_ids`
- `answer`
- `citations`
- `created_at`

### `kg_triples`

Purpose:

- graph construction
- graph retrieval
- entity-centric browsing

Minimum fields:

- `id`
- `doc_id`
- `subject`
- `predicate`
- `object`
- `confidence`

Indexes:

- subject
- object

### `classification_feedback`

Purpose:

- user-corrected labels
- few-shot examples for future classification prompts

Minimum fields:

- `id`
- `doc_id`
- `original_label`
- `corrected_label`
- `created_at`

### Migrations

Database evolution must move under Alembic. Manual ad hoc schema mutation inside service startup is no longer acceptable as the primary migration mechanism.

The schema rollout for this rebuild must explicitly cover:

- new document summary and duplicate fields
- entity persistence
- QA session history
- graph triples
- classification feedback

## Frontend Architecture

The Vue frontend remains in `frontend/docagent-frontend/`, but the rebuild expands the application into a document assistant rather than only a search UI.

### New Pages

#### `QAPage.vue`

Capabilities:

- document selection
- free-form question input
- streaming answer display
- citation chips
- jump-to-document navigation

#### `GraphPage.vue`

Capabilities:

- entity relationship graph
- node click filtering
- graph-to-document linkage

### Search Page Changes

The search experience must surface model reasoning, not hide it.

Required additions:

- query analysis bar showing inferred intent and expansions
- add-to-QA action on result cards
- entity highlighting in snippets
- better document-level explanation of why a result matched

Recommended component boundaries:

- `QueryAnalysisBar`
- `DocumentResultList`
- `EntityHighlight`

### Documents Page Changes

Required additions:

- short LLM summary on each document card
- detailed summary expansion
- duplicate warning
- batch actions for summarize, reclassify, and export

The documents view should remain document-centric and operational, not become a raw block browser.

### Streaming

The frontend must support SSE or equivalent streaming for QA so answers can render incrementally.

## Migration Strategy

This rebuild replaces the core while keeping the application runnable during delivery.

### Phase Model

The migration should proceed in layered replacement order:

1. infrastructure hardening
2. domain extraction and indexing replacement
3. ingest pipeline replacement
4. retrieval replacement
5. QA and graph feature delivery
6. legacy `utils` retirement

### Compatibility Rules

- existing routes may call new services temporarily
- legacy services may delegate into new domain modules during migration
- no new user-facing capability should deepen dependency on old `utils` modules
- once a domain module is in place, the equivalent legacy utility should stop being the source of truth

### Legacy Retirement Targets

The following categories are intended to be replaced:

- parsing and normalization logic currently in `backend/utils/document_processor.py`
- block extraction logic currently in `backend/utils/block_extractor.py` or equivalent legacy indexing helpers
- retrieval logic currently centered on `backend/utils/retriever.py`
- scattered LLM orchestration in `backend/utils/smart_retrieval.py` and similar modules

## Explicit Defect Fixes Included In Scope

The rebuild scope explicitly includes currently known defects and inconsistencies:

1. restore the missing delete route decorator so document deletion is exposed correctly through the API
2. add block extraction support for Excel and PPT so block indexing is not limited to PDF and DOCX
3. eliminate remaining architecture cases where `app/services` is only a thin wrapper around legacy `utils`

## Observability And Reliability

The rebuilt system must expose enough state to debug ingest and retrieval behavior.

Required operational visibility:

- per-document ingest stage status
- provider and model selection logs
- token usage by task type
- index rebuild status
- QA session history
- duplicate detection markers

Caching should be used where safe, especially for deterministic query analysis and document extraction prompts, but cache usage must not obscure source-of-truth persistence.

## Security And Data Handling

The product remains local-first and file-based. Secrets stay in environment variables or the existing local secrets mechanism. The rebuild does not introduce remote data synchronization.

Sensitive design constraints:

- LLM providers may receive document excerpts, so provider choice must stay configurable
- local fallback models should remain possible for privacy-sensitive use
- raw files remain in the local file store

## Acceptance Criteria

The rebuild is considered functionally complete when the following are true:

1. all new core features operate through `app/domain` and `app/services`, not legacy `utils` as the source of truth
2. ingest supports normalized block generation for PDF, DOCX, XLSX, and PPTX at minimum
3. documents persist LLM metadata, entities, QA history, and graph triples in the database
4. retrieval performs query analysis, multi-route recall, fusion, and reranking
5. QA supports streaming answers with citations
6. graph view can render extracted entity relations and filter documents by graph node
7. delete behavior is correctly exposed by the API and works end to end
8. Alembic manages the schema required for the rebuild

## Delivery Order

Implementation should still be phased even though the target design is a complete rebuild.

Recommended delivery order:

1. unify LLM gateway, add Alembic, fix delete route, and close format support gaps for Excel and PPT
2. build the new ingest pipeline with structured metadata extraction, entities, and triples
3. replace retrieval with query analysis, hybrid recall, RRF fusion, and reranking
4. deliver QA service and streaming UI
5. deliver graph extraction and graph UI
6. add classification feedback, batch operations, export, and observability polish

This preserves demoability while still converging on the full target architecture.

## Risks And Mitigations

### Scope Risk

This is a large rebuild affecting backend architecture, database schema, search behavior, and frontend interaction. The mitigation is phased implementation with a stable spec and explicit migration boundaries.

### Provider Reliability Risk

LLM-heavy workflows increase sensitivity to provider latency and rate limits. The mitigation is a centralized gateway with retries, fallback providers, and caching.

### Retrieval Quality Risk

Adding more retrieval routes can degrade result quality if not fused and grounded properly. The mitigation is structured query analysis, RRF fusion, and citation-preserving document regrouping.

### Parser Heterogeneity Risk

Office formats produce different structures and extraction quality. The mitigation is a normalized extractor contract with format-specific adapters and consistent block schemas.

## Design Decision Summary

This rebuild makes four explicit decisions:

1. the system is a document knowledge assistant for individuals and small teams, not a loose classification demo
2. LLMs are embedded throughout the core chain instead of being limited to labeling and reranking
3. `app/domain` becomes the permanent core and `utils` becomes transitional legacy code
4. graph and QA capabilities are required product features, not optional later polish

This document is the authoritative design for the complete rebuild.
