# DocAgent Modular LightRAG-Core Architecture Design

## Context

The current DocAgent codebase is runnable, but its robustness is limited by architectural drift rather than by isolated implementation bugs.

Observed structural issues in the repository:

- the backend mixes a newer `backend/app/*` shell with direct imports from legacy `backend/utils/*`
- business state is split across SQLite metadata, filesystem state, Chroma, in-memory task state, and LightRAG sync markers
- startup and runtime concerns are coupled into `backend/main.py`
- service code mixes synchronous logic, async logic, raw threads, process management, and ad hoc reconciliation
- external dependencies such as LightRAG and local embedding runtime are treated partly as infrastructure and partly as application state

This design defines a pragmatic target architecture that:

1. keeps existing user-facing functionality largely intact during migration
2. treats LightRAG as a long-term core dependency
3. improves modular boundaries so future AI-assisted changes can be small, local, and safe
4. keeps the system easy to start, test, and maintain in a local-first environment

## Goals

1. Make LightRAG a first-class, long-term core knowledge engine for ingest, retrieval, QA, and graph exploration.
2. Make SQLite the single source of truth for business control state.
3. Replace direct business-layer dependence on `backend/utils/*` with explicit adapters and bounded module contracts.
4. Reorganize the backend into modules with small, clear responsibilities and stable public entry points.
5. Preserve current `/api/v1` behavior during migration and allow gradual adoption of `/api/v2`.
6. Improve startup, operability, and failure recovery without requiring a distributed platform.

## Non-Goals

1. Rewriting the entire product in one pass.
2. Removing LightRAG from the architecture.
3. Converting the project into microservices.
4. Requiring cloud-native infrastructure or heavy orchestration.
5. Perfecting every parser, OCR path, or retrieval heuristic in the same effort.

## Architectural Principles

### 1. Modular Monolith First

The target system is a modular monolith, not a microservice system.

Rationale:

- current deployment and usage are local-first
- current failure modes are caused by weak internal boundaries, not by lack of network boundaries
- a modular monolith reduces operational complexity while still enforcing architecture
- AI-assisted changes are safer when the change surface is a bounded module instead of a distributed graph of services

### 2. LightRAG Is Core, But Not the Business State Source

LightRAG remains a mandatory core dependency for knowledge operations. It is not treated as optional enhancement.

LightRAG is responsible for:

- semantic ingest
- semantic retrieval
- graph-oriented evidence
- QA context generation
- semantic snapshots and cross-document knowledge access

SQLite remains responsible for:

- document registration
- document lifecycle state
- ingest jobs and retries
- classification review state
- auditability
- local identifiers and citation traceability

This avoids coupling the entire application state model to LightRAG internals while still making LightRAG central to product value.

### 3. One Business Fact, One Canonical Owner

Every important business fact must have one canonical owner:

- document lifecycle state: SQLite
- source file location and file availability: file store plus SQLite pointer
- semantic and graph knowledge: LightRAG
- local preview blocks and block anchors: local persistence
- runtime event history: SQLite event log

The system must stop inferring truth by comparing several partially overlapping stores at request time.

### 4. Ports and Adapters for Change Isolation

All external dependencies and legacy code paths must be wrapped behind ports and adapters.

This includes:

- LightRAG
- local embedding runtime
- filesystem storage
- vector store access
- legacy `utils/*` logic
- LLM providers

The application and domain layers may depend on interfaces and stable DTOs, but not on raw clients, response payloads, or legacy helpers.

### 5. Small Modules With Stable Public Entry Points

Every business module must have:

- one clear responsibility
- a small set of public use cases
- explicit allowed dependencies
- explicit forbidden dependencies
- module-local tests
- a short module README for humans and AI agents

If a future change to retrieval requires reading classification internals, LightRAG client code, raw SQLite code, and two legacy utils files, the module design has failed.

## Target System Topology

```text
Frontend (Vue 3)
  |
  | HTTP / SSE
  v
FastAPI API
  |
  v
Module Application Services
  |
  v
Ports / Contracts
  |
  +--> LightRAG Gateway
  +--> File Store
  +--> Local Block Store
  +--> LLM Gateway
  +--> Legacy Adapters (temporary)
  |
  v
Persistence and Knowledge Plane
  +--> SQLite
  +--> Filesystem
  +--> LightRAG
  +--> Chroma or local vector cache if still needed
```

## Target Backend Directory Structure

```text
backend/
├── main.py
├── worker.py
├── config.py
├── app/
│   ├── bootstrap/
│   │   ├── app_factory.py
│   │   ├── lifespan.py
│   │   ├── settings.py
│   │   ├── deps.py
│   │   └── router.py
│   ├── platform/
│   │   ├── errors.py
│   │   ├── result.py
│   │   ├── events.py
│   │   ├── task_queue.py
│   │   ├── idempotency.py
│   │   ├── telemetry.py
│   │   └── sqlite.py
│   ├── modules/
│   │   ├── documents/
│   │   ├── ingest/
│   │   ├── retrieval/
│   │   ├── qa/
│   │   ├── classification/
│   │   ├── graph/
│   │   └── runtime/
│   └── adapters/
│       ├── lightrag/
│       ├── legacy/
│       ├── storage/
│       └── llm/
└── alembic/
```

The horizontal `services/domain/infra` model is replaced by vertical business modules. Each module may still contain internal layering, but the repository structure itself follows business capability boundaries.

## Module Boundaries

### Documents Module

Responsibility:

- upload registration
- document metadata view
- file fetch
- delete orchestration
- version selection

Public entry points:

- `DocumentService.upload`
- `DocumentService.get`
- `DocumentService.list`
- `DocumentService.delete`

Allowed dependencies:

- platform primitives
- ingest contracts
- file store adapter

Forbidden dependencies:

- direct LightRAG HTTP calls
- direct legacy utils imports

### Ingest Module

Responsibility:

- extraction workflow
- version creation
- block generation
- local persistence
- LightRAG sync
- retry and recovery

Public entry points:

- `IngestService.enqueue`
- `IngestService.run_next_job`
- `IngestService.retry`
- `IngestService.get_status`

Allowed dependencies:

- documents contracts
- LightRAG gateway
- storage adapters
- temporary legacy extraction adapters

Forbidden dependencies:

- FastAPI
- direct frontend-oriented response shaping

### Retrieval Module

Responsibility:

- query planning
- LightRAG recall
- local citation enrichment
- ranking and result formatting

Public entry points:

- `RetrievalService.search`
- `RetrievalService.explain`

Allowed dependencies:

- LightRAG gateway
- documents contracts
- ingest contracts

Forbidden dependencies:

- direct raw database access outside repository
- direct imports from legacy utils after migration completes

### QA Module

Responsibility:

- question answering over retrieved context
- streamed answers
- citation packaging
- QA session storage

### Classification Module

Responsibility:

- classification assignment
- taxonomy handling
- review workflow
- feedback persistence

### Graph Module

Responsibility:

- entity and relation graph payloads
- graph-focused search responses
- graph view model shaping

### Runtime Module

Responsibility:

- health and dependency reporting
- audit reports
- repair jobs
- operational visibility

## LightRAG Integration Model

LightRAG is elevated into a dedicated adapter package and becomes the canonical semantic engine.

### Required Adapter

`app/adapters/lightrag/gateway.py` defines a stable application-facing contract.

Representative operations:

- `ingest_document`
- `delete_document`
- `get_ingest_status`
- `search`
- `query_context`
- `graph`
- `get_document_snapshot`

### Adapter Rules

1. Only the LightRAG adapter knows LightRAG HTTP paths and raw payload shapes.
2. Business modules consume typed internal DTOs, not raw JSON from LightRAG.
3. Any LightRAG payload that becomes user-facing must be normalized into local identifiers and response models first.
4. Changes to LightRAG API behavior must be isolated to adapter code and adapter tests whenever possible.

### Citation and Identity Resolution

The project must maintain local identity as the user-facing authority:

- `document_id`
- `version_id`
- `block_id`

LightRAG-origin evidence must be mapped back to those identifiers before being returned to retrieval, QA, or graph endpoints. This keeps preview, deletion, retries, and UI linking stable even if LightRAG response formats evolve.

## Data Plane Design

The target architecture uses a dual-plane model.

### Business Control Plane: SQLite

SQLite owns:

- document lifecycle state
- version lineage
- ingest job state
- classification review state
- runtime events
- local content and block metadata needed for preview and citations

### Knowledge Plane: LightRAG

LightRAG owns:

- semantic indexing
- graph-style retrieval support
- semantic context snapshots
- QA-oriented context generation

### File Plane: Filesystem

Filesystem owns:

- original uploaded file bytes
- derived local artifacts when needed

### Derived Plane: Rebuildable Caches

Optional local vector or graph cache layers are allowed, but they are rebuildable derivatives. They must never be the only authoritative location of business-critical state.

## Data Model

The existing broad `payload`-centric persistence should be migrated toward explicit tables.

### Required Core Tables

`documents`

- `document_id`
- `filename`
- `file_type`
- `file_size`
- `file_path`
- `content_hash`
- `lifecycle_status`
- `active_version_id`
- `created_at`
- `updated_at`
- `deleted_at`

`document_versions`

- `version_id`
- `document_id`
- `content_hash`
- `parser_profile`
- `extracted_text_hash`
- `block_count`
- `status`
- `created_at`

`document_contents`

- `version_id`
- `full_content`
- `preview_content`
- `parser_name`
- `extraction_status`
- `extraction_error`
- `updated_at`

`document_blocks`

- `block_id`
- `document_id`
- `version_id`
- `block_index`
- `block_type`
- `content`
- `heading_path`
- `page_number`
- `sheet_name`
- `slide_number`
- `content_hash`

`ingest_jobs`

- `job_id`
- `document_id`
- `version_id`
- `job_type`
- `status`
- `stage`
- `attempt_count`
- `max_attempts`
- `error_code`
- `error_message`
- `next_retry_at`
- `started_at`
- `finished_at`
- `created_at`

`lightrag_documents`

- `document_id`
- `version_id`
- `lightrag_doc_id`
- `lightrag_track_id`
- `sync_status`
- `last_synced_at`
- `last_error`
- `remote_content_hash`

`classifications`

- `classification_id`
- `document_id`
- `version_id`
- `label`
- `label_path`
- `confidence`
- `source`
- `review_status`
- `explanation`
- `created_at`
- `updated_at`

`runtime_events`

- `event_id`
- `module`
- `aggregate_id`
- `event_type`
- `severity`
- `payload`
- `created_at`

### Migration Note

The existing `payload` JSON field may remain temporarily for compatibility reads during migration, but it should cease to be the primary write model for new architecture paths.

## Lifecycle and Job State Machines

### Document Lifecycle

```text
registered
  -> stored
  -> extracting
  -> extracted
  -> indexing_local
  -> syncing_lightrag
  -> ready
```

Failure and degraded branches:

```text
extracting -> failed_extract
indexing_local -> degraded_local_index
syncing_lightrag -> degraded_lightrag
any_active_state -> failed
ready -> deleting -> deleted
```

Interpretation:

- `ready`: both business and semantic operations are available
- `degraded_lightrag`: local document exists, but core LightRAG-backed knowledge features are impaired
- `degraded_local_index`: LightRAG may be healthy, but local preview/citation support is damaged
- `failed_extract`: content could not be normalized into the ingest chain

### Ingest Job Lifecycle

```text
queued
  -> running
  -> waiting_lightrag
  -> succeeded
```

Failure branches:

```text
running -> retryable_failed -> queued
waiting_lightrag -> retryable_failed -> queued
running -> terminal_failed
waiting_lightrag -> terminal_failed
```

All retries, repairs, and recovery must work through persisted jobs, not through in-memory process state.

## API Strategy

### `/api/v1`

`/api/v1` remains active during migration and preserves current frontend expectations.

Implementation rule:

- `/api/v1` may call new module services via compatibility shims
- `/api/v1` must not become the driver of new architecture decisions

### `/api/v2`

`/api/v2` becomes the canonical contract for the new modular architecture.

Recommended areas:

- `/api/v2/documents`
- `/api/v2/ingest`
- `/api/v2/retrieval`
- `/api/v2/qa`
- `/api/v2/classification`
- `/api/v2/graph`
- `/api/v2/runtime`

## Startup and Runtime Design

### App Startup

`main.py` becomes a thin bootstrap entry point that calls `create_app()`.

Startup responsibilities are limited to:

- loading settings
- constructing routers
- wiring dependencies
- registering middleware
- performing lightweight dependency checks

### Worker Runtime

A separate `worker.py` handles:

- ingest jobs
- retries
- repair actions
- background audit tasks

This removes long-running business processing from the FastAPI request process and improves restart safety.

### Health Model

Health endpoints are split conceptually into:

- liveness: the API process responds
- readiness: the application is ready to accept traffic
- dependency health: LightRAG, SQLite, filesystem, embedding runtime

The system must stop representing dependency impairment as fake success or empty business results.

## Legacy Containment Strategy

Legacy `backend/utils/*` code is not removed in the first migration wave. It is quarantined.

Required package:

```text
app/adapters/legacy/
  document_processor_adapter.py
  retriever_adapter.py
  smart_retrieval_adapter.py
```

Rules:

1. New module code may depend on legacy adapters temporarily.
2. New module code may not import `utils.*` directly.
3. Legacy adapters must be treated as migration boundaries, not as permanent API.
4. As replacement domain logic lands, legacy adapter call sites are removed module by module.

## Testing Strategy

Testing moves from mixed repository-wide regression habits toward module contract testing plus compatibility protection.

### Compatibility Tests

Preserve current behavior for migration safety:

- `backend/test/compat/test_v1_documents_behavior.py`
- `backend/test/compat/test_v1_retrieval_behavior.py`
- `backend/test/compat/test_v1_classification_behavior.py`
- `backend/test/compat/test_v1_qa_behavior.py`

### Module Tests

Each module gains focused tests:

- service contract tests
- repository tests
- adapter tests
- state machine tests where relevant

Recommended layout:

```text
backend/test/modules/
  documents/
  ingest/
  retrieval/
  qa/
  classification/
  graph/
  runtime/
```

### Adapter Tests

LightRAG adapter tests are mandatory because LightRAG is a core dependency. They must verify:

- request mapping
- response mapping
- status polling behavior
- error translation
- idempotent retry behavior where possible

## AI-Friendly Code Organization Rules

These rules are part of the architecture, not merely coding style preferences.

1. Every business module must include a short `README.md` documenting:
   - responsibility
   - public entry points
   - allowed dependencies
   - forbidden dependencies
   - test command
2. No business file should grow into a catch-all orchestration file comparable to the current large services and legacy utils.
3. Public service methods must return typed DTOs or result objects, not arbitrary dictionaries.
4. FastAPI-specific code must remain inside API files.
5. Raw LightRAG payload handling must remain inside the LightRAG adapter package.
6. Direct raw SQLite access must remain inside repositories or platform persistence helpers.
7. Cross-module interaction must happen through contracts or explicitly exposed service methods.

These rules reduce the context window required for safe AI changes and make the cost of architectural drift visible.

## Migration Plan

The migration proceeds in six phases.

### Phase 0: Behavior Freeze and Smoke Baseline

- add `/api/v1` compatibility tests
- add smoke startup and upload/search verification scripts
- document current runtime dependencies

### Phase 1: Bootstrap and Settings Refactor

- introduce `app/bootstrap/*`
- move app creation into factory pattern
- reduce `main.py` to thin startup code

### Phase 2: Platform Layer and LightRAG Gateway

- add `app/platform/*`
- add `app/adapters/lightrag/*`
- make LightRAG interaction go through a stable gateway

### Phase 3: Legacy Adapter Quarantine

- introduce `app/adapters/legacy/*`
- route old utils access through adapters
- ban new direct `utils.*` imports in business code

### Phase 4: Documents and Ingest State Machine

- create `documents` and `ingest` modules
- add explicit lifecycle and job persistence
- route upload and ingest through persisted workflow

### Phase 5: Retrieval, QA, and Graph Rebuild

- create `retrieval`, `qa`, and `graph` modules
- move semantic core behavior onto LightRAG gateway and local citation resolution

### Phase 6: Classification, Runtime, and Legacy Cleanup

- create `classification` and `runtime` modules
- shift health, audit, and repair logic out of main startup flow
- reduce and eventually remove legacy adapters where replaced

## Operational Impact

### What Changes

- internal structure becomes module-oriented
- startup becomes simpler and more predictable
- retries and reconciliation become job-driven rather than memory-driven
- LightRAG becomes more central and more explicitly integrated
- failure states become visible and classifiable instead of being hidden behind fallback success

### What Stays Stable

- the product remains a local-first FastAPI plus Vue application
- `/api/v1` remains available during migration
- current major user-visible capabilities remain in place
- LightRAG remains part of the long-term product core

## Risks and Mitigations

### Risk: Migration Becomes an Endless Hybrid State

Mitigation:

- enforce direct-import bans for `utils.*` from new modules
- track legacy adapter call sites explicitly
- require module README and contract tests before declaring a migrated module complete

### Risk: LightRAG Core Dependency Increases Blast Radius

Mitigation:

- isolate LightRAG behind gateway contract
- keep SQLite as canonical business state
- distinguish degraded dependency state from total business failure

### Risk: Existing Frontend Breakage During Migration

Mitigation:

- preserve `/api/v1`
- add compatibility tests
- normalize responses through compatibility shims before exposing new contracts broadly

### Risk: Background Work Still Leaks Into the API Process

Mitigation:

- move long-running ingest and repair work into `worker.py`
- persist jobs and retries in SQLite

## Decision Summary

The approved target architecture is:

- a modular monolith
- with LightRAG as a long-term core semantic dependency
- with SQLite as the business control-plane source of truth
- with vertical business modules as the main organizational unit
- with ports and adapters isolating LightRAG, legacy logic, and other external systems
- with a gradual migration path that preserves current functionality during the transition

This architecture is intended not only to improve robustness, but also to make future human and AI modifications smaller, more localized, and less likely to damage unrelated behavior.
