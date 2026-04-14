# Startup Warmup Pipeline Design

## Scope

Refactor the system so backend processing results are persisted and reused across restarts, and so service startup triggers a background warmup pipeline instead of forcing the frontend to synchronously recompute heavy work.

Goals:

- Persist document processing results for:
  - text extraction
  - vector chunks
  - reader block index
  - LLM classification
  - corpus topic tree
- Reuse completed LLM classification results after restart when the document content has not changed.
- Start the API quickly, then warm documents in the background with low concurrency.
- Keep search usable while warmup is still running.
- Stop the frontend from blocking on synchronous topic-tree generation.

Out of scope:

- Pre-generating query-specific summaries or classification reports.
- Introducing a separate worker service or external queue.
- Reworking the existing retrieval ranking algorithms beyond making their prerequisites ready earlier.

## Current Problems

The repository already persists document metadata, extracted content, segments, document artifacts, and global artifacts in SQLite, but the startup path does not assemble these pieces into a single warmup lifecycle.

Observed runtime problems:

- Startup checks only inspect vector chunk presence and do not complete block indexing, classification, or topic-tree preparation.
- Topic tree generation is still triggered from read paths when no cached tree is available.
- Topic tree generation hard-fails when the LLM request times out, which makes the frontend appear broken even though core search can still work.
- Search and taxonomy pages currently treat topic-tree loading as a required first-screen dependency.
- The documents table has state fields (`status`, `error_message`, `retry_count`), but there is no single pipeline state model that answers which processing layers are ready and which are stale.

## Processing Model

### Per-Document Readiness State

Each document keeps a persisted readiness record inside its metadata payload. The record is stored in the existing SQLite-backed document payload and updated through the existing metadata store APIs.

Required fields:

- `content_hash`
- `content_signature_version`
- `chunk_status`
- `chunk_content_hash`
- `chunk_pipeline_version`
- `block_index_status`
- `indexed_content_hash`
- `index_version`
- `classification_status`
- `classification_hash`
- `classification_model`
- `classification_completed_at`
- `last_processed_at`
- `error_message`

Status values:

- `missing`
- `pending`
- `processing`
- `ready`
- `failed`
- `stale`

This state is document-centric. A document can be:

- ready for search but still missing classification
- ready for classification reuse but stale for block indexing
- fully ready for all startup-managed layers

### Reuse Rule

The reuse rule is content-based, not document-ID-based.

- If `classification_status == ready` and `classification_hash == current content_hash`, restart must reuse the existing classification result and must not call the LLM again.
- If the content hash changes, classification becomes `stale` and must be recomputed.
- Chunk and block-index readiness follow the same rule, using their own stored content-hash fields plus pipeline version fields.

### Global Topic Tree State

The topic tree remains a global artifact, but it must store enough metadata to decide whether it is reusable.

Required fields:

- `schema_version`
- `generation_method`
- `generated_at`
- `status`
- `corpus_fingerprint`
- `source_document_count`
- `topic_count`
- `last_error`
- `topics`

`corpus_fingerprint` is derived from the set of document IDs plus their classification-ready content hashes. If the fingerprint matches the cached artifact, restart reuses the existing tree. If it differs, the cached tree becomes `stale` until the background rebuild completes.

## Startup and Warmup Flow

### Service Startup

`backend/main.py` keeps startup lightweight:

- create required directories
- initialize Chroma
- lock embedding dimension
- load existing metadata/artifacts
- start the API
- launch the warmup coordinator in the background

Startup must no longer block on rebuilding all document artifacts before the service becomes available.

### Warmup Coordinator

Add a backend-only `WarmupCoordinator` service responsible for startup scanning and background execution.

Responsibilities:

- scan all documents on startup
- compute missing or stale processing stages per document
- run the document pipeline in priority order
- rebuild the global topic tree only after document-level prerequisites are stable
- expose current warmup progress for the frontend

Concurrency:

- low and bounded, default `1-2` concurrent documents
- topic-tree rebuild runs as a single global task after document tasks

### Document Pipeline Order

For each document, the coordinator executes:

1. Extraction validation
   - If extracted content or `content_hash` is missing, or the source file signature changed, re-run extraction and persist `content_hash`.
2. Chunk validation
   - If vector chunks are missing, stale, or version-mismatched, rebuild chunks and invalidate retrieval caches.
3. Reader block index validation
   - If `block_index_status != ready`, or `indexed_content_hash != current content_hash`, rebuild `reader_blocks`.
4. Classification validation
   - If classification is missing or stale, run LLM classification and persist the result with `classification_hash`.
   - If classification is still valid for the current content hash, reuse it without LLM.

After all documents finish these stages, the coordinator evaluates whether the topic tree needs rebuilding.

### Topic Tree Build Policy

Topic tree generation must move out of the first-read path.

- `get_topic_tree()` should return cached data if available.
- If the cached tree is missing or stale, it should return state metadata indicating that background preparation is needed or in progress.
- The warmup coordinator, not the frontend read path, owns automatic rebuilds.
- Manual rebuild endpoints remain available and explicitly override cache reuse.

Topic-tree rebuild prerequisites:

- document extraction ready
- document chunks ready
- document block index ready
- document classification ready or validly reused

If a rebuild fails:

- keep the previous successful tree
- mark the artifact status as `stale` or `failed`
- record `last_error`
- do not break search or other pages

## API Design

### New Warmup Status Endpoint

Add:

- `GET /api/v1/system/warmup-status`

Response fields:

- `warmup_running`
- `total_documents`
- `documents_ready_for_search`
- `documents_chunk_ready`
- `documents_block_ready`
- `documents_classification_ready`
- `documents_failed`
- `queue_depth`
- `active_tasks`
- `topic_tree_status`
- `topic_tree_generated_at`
- `topic_tree_stale`
- `recent_errors`

This endpoint is read-only and cheap. It is the frontend’s polling source.

### Existing Document APIs

Document list/detail payloads should surface readiness fields already persisted in metadata, such as:

- `chunk_status`
- `block_index_status`
- `classification_status`
- `classification_result`
- `error_message`

This lets the UI show per-document readiness without extra heavy requests.

### Existing Topic Tree APIs

`GET /api/v1/classification/topic-tree` should return:

- cached tree payload when available
- empty `topics` with explicit status metadata when not yet ready

It must not synchronously trigger a fresh LLM-based rebuild from the request path.

`POST /api/v1/classification/topic-tree/build` remains the manual rebuild action and should mark the tree as rebuilding before dispatching the work.

## Frontend Behavior

### Search Page

Search page initialization must not bundle topic-tree loading into a required `Promise.all()` gate.

Required change:

- load stats and categories independently
- load cached topic tree independently
- tolerate topic-tree failure without breaking the rest of the page

UI behavior:

- search remains usable even if warmup is still running
- topic-tree panel shows one of:
  - `ready`
  - `building`
  - `stale`
  - `missing`
  - `failed`
- when warmup status changes from `building/stale` to `ready`, the page refetches the topic tree once

### Taxonomy Page

Taxonomy page should read cached topic-tree state and render a non-fatal empty or stale state when background generation is incomplete.

It must not be the place where heavy topic-tree generation first happens.

### Polling Strategy

Frontend uses low-frequency polling against `warmup-status`, for example every `5-10` seconds.

Polling responsibilities:

- refresh progress text
- refresh per-document readiness markers if needed
- refetch topic tree only when its status transitions to `ready`

## Error Handling

### Document-Level Failures

A failure in one document must not block the rest of the warmup queue.

On failure:

- set the relevant stage status to `failed`
- store a short error message
- increment retry count
- continue with the next document

### Retry Policy

Automatic retries are allowed across restarts, but they must remain bounded by persisted status and retry counters. The system should avoid an unbounded tight loop that repeatedly hits the same LLM or indexing failure during a single startup.

### Topic Tree Failures

Topic-tree rebuild failure must be isolated.

- keep last good artifact if present
- expose `stale` or `failed`
- show the issue in warmup status
- never make the whole frontend unusable

## Logging and Observability

Startup logs should include a warmup summary:

- total documents
- chunk-missing count
- block-index-missing count
- classification-missing count
- topic-tree reuse vs rebuild decision

Warmup logs should include stage-level transitions with document ID and filename.

This replaces the current misleading behavior where different chunk-check paths report contradictory health results.

## Validation

Implementation is complete when:

1. Restart does not recompute LLM classification for documents whose `content_hash` has not changed.
2. Search remains usable while warmup is running.
3. Topic tree is no longer rebuilt from the first frontend read path.
4. Search page and taxonomy page stay functional when topic-tree warmup is pending or failed.
5. Topic tree rebuild reuses the prior cached tree on failure.
6. Startup scan and on-demand chunk checks use the same chunk-readiness rules.
7. Warmup status is visible through a lightweight backend endpoint.

## Test Plan

Required automated coverage:

- startup scan correctly distinguishes:
  - fully ready documents
  - missing chunk documents
  - stale block-index documents
  - stale classification documents
- unchanged content reuses classification without LLM calls
- changed content invalidates classification and topic-tree fingerprints
- cached topic tree is returned without synchronous rebuild
- failed topic-tree rebuild preserves the previous cached tree and marks it stale
- search-page initialization tolerates topic-tree request failure
- warmup-status reflects active progress and failures

## Risks

- Existing document metadata is inconsistent across historical data; migration logic must default missing readiness fields safely.
- Some older documents may have chunks but no extracted content hash, requiring a one-time extraction backfill.
- Topic-tree fingerprints must be deterministic, or the system will rebuild too often.
- Low-concurrency background warmup is intentionally slower than full parallelism, but this is preferred to reduce memory pressure and LLM burst failures.
