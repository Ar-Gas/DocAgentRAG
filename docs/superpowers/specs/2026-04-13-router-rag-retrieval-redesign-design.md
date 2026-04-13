# Router RAG Retrieval Redesign

## Context

The current retrieval stack is document-centric at the UI level but still chunk-centric in the backend. The existing pipeline is effectively:

1. extract plain text
2. chunk text
3. run vector / BM25 / hybrid retrieval
4. group chunk hits back into documents

This is not sufficient for real office documents. It loses heading hierarchy, table structure, page context, and document semantics. It also makes the system poor at precise clause retrieval in Word/PDF documents, which is the user's top priority for the first implementation phase.

The long-term target is not “one better retriever.” It is a routed retrieval system where the query type determines which retrieval path should answer it.

## Goals

1. Redesign retrieval around a routed architecture instead of a single chunk pipeline.
2. Define a long-term Router RAG architecture that supports:
   - Word/PDF clause retrieval
   - Excel data QA through a dedicated execution path
   - cross-document summarization / macro questions
   - multimodal page understanding for complex PDF/PPT pages
3. Define a first implementation phase that materially improves Word/PDF retrieval accuracy without requiring the full end-state stack.
4. Preserve compatibility with the current FastAPI + frontend workspace during the first phase.

## Non-Goals

1. Fully implement Excel agentic QA in phase one.
2. Fully implement graph-enhanced retrieval in phase one.
3. Fully implement multimodal page QA in phase one.
4. Replace the current frontend workspace interaction model in phase one.

## Product Strategy

The redesign should be treated as two layers:

### Layer 1: End-State Router RAG

The system becomes a retrieval router that chooses the correct retrieval path based on the query and the target evidence type.

### Layer 2: Phase-One Block Retrieval

The first delivery should focus on Word/PDF retrieval quality. It should replace the current naive chunk retrieval core with structure-aware block retrieval, hybrid recall, reranking, and document-level evidence aggregation.

This means the first phase must be useful on its own, but also align with the long-term router architecture.

## End-State Architecture

The end-state system should be composed of five layers.

### 1. Ingestion Layer

Each document is parsed into typed structural units instead of anonymous fixed-size chunks.

Examples:

- Word/PDF:
  - heading blocks
  - paragraph blocks
  - list blocks
  - table blocks
- Excel:
  - workbook metadata
  - worksheet metadata
  - table region metadata
  - header schemas
- PPT/PDF visual pages:
  - page image artifacts
  - OCR / layout artifacts

The ingestion layer is responsible for preserving logical structure and context.

### 2. Index Layer

The same source document should feed multiple index types rather than one shared chunk index.

Recommended index families:

- BM25 / inverted index for exact term and identifier matching
- vector index for semantic recall
- document summary index for macro retrieval
- metadata index for filename / classification / date / parser fields
- optional graph / entity index for cross-document relationship reasoning

### 3. Retrieval Router

The router decides which retrieval path to use.

Examples:

- clause lookup in Word/PDF -> hybrid block retrieval + reranker
- Excel calculation / filtering question -> Excel execution path
- corpus-level summary question -> document-summary / graph path
- visual chart question -> multimodal page path

The router is the system boundary that replaces the current “every question hits the same retriever” behavior.

### 4. Evidence Composer

The system should produce evidence cards rather than raw chunks.

Each evidence card should describe:

- document identity
- block identity
- block type
- heading path
- page number or table location
- snippet
- retrieval score
- match reason

### 5. Answer Layer

The answering layer should consume ranked evidence cards instead of arbitrary top-K chunks.

This layer can support:

- direct retrieval response
- extractive answer generation
- citation-rich summaries
- routed agent outputs

## End-State Routes

The long-term router should support at least these paths:

### Route A: Structured Clause Retrieval

For Word/PDF policy, contract, report, and narrative documents.

Primary mechanism:

- structured blocks
- BM25 + vector hybrid recall
- reranking
- document evidence aggregation

### Route B: Excel Data QA

Excel should not be treated as ordinary retrieval text.

Primary mechanism:

- workbook / sheet structure parsing
- dataframe or table execution path
- optional text-to-Python or text-to-SQL orchestration

### Route C: Cross-Document Macro Retrieval

For questions like “summarize the strategy across 50 annual reports.”

Primary mechanism:

- document-level summaries
- representative evidence cards
- optional graph / topic / entity support

### Route D: Multimodal Visual Retrieval

For chart-heavy or layout-heavy PDF/PPT pages.

Primary mechanism:

- page image rendering
- OCR / layout artifacts
- multimodal model reasoning

## Phase-One Scope

Phase one should focus only on Route A: structured clause retrieval for Word/PDF.

It should deliver:

1. structure-aware block extraction for Word/PDF
2. hybrid retrieval over blocks
3. reranking over recalled blocks
4. document-level evidence aggregation
5. reader payloads based on structural blocks instead of coarse plain-text paragraphs

It should not require Excel routing, graph indexing, or multimodal QA to be complete.

## Phase-One Data Model

Phase one should use `Block` as the core retrieval unit instead of the current naive chunk.

Each block should include at minimum:

- `block_id`
- `document_id`
- `file_type`
- `block_type`
- `text`
- `heading_path`
- `section_title`
- `page_number`
- `order_index`
- `keywords`
- `table_caption`
- `source_parser`

### Phase-One Block Schema

The minimum schema should be treated as:

- `block_id: str`
- `document_id: str`
- `file_type: str`
- `block_type: str`
- `text: str`
- `heading_path: list[str]`
- `section_title: str | null`
- `page_number: int | null`
- `order_index: int`
- `keywords: list[str]`
- `table_caption: str | null`
- `source_parser: str`

Field derivation rules:

- `section_title` may be `null` when no reliable local title can be inferred
- `page_number` is required for PDF blocks when available from the parser, and may be `null` for DOCX blocks
- `keywords` may be an empty list if no explicit keyword extraction runs in phase one
- `table_caption` may be `null` for non-table blocks and for table blocks without a reliable caption source

### `block_id` Stability

`block_id` must be deterministic for the same indexed document version so the existing reader anchor flow can rely on it.

Phase-one rule:

- `block_id` should be derived from `document_id + index_version + order_index`
- the same document content re-indexed under the same `index_version` must preserve the same `block_id`
- if block structure changes because the indexing version changes, the `index_version` change is allowed to invalidate old `block_id` values

This keeps anchors stable within one index generation while making versioned reindexing explicit.

### Block Types

Phase one should at least support:

- `heading`
- `paragraph`
- `list`
- `table`

### Extraction Rules

- Word and PDF should preserve heading hierarchy where possible.
- Tables should remain intact as single logical blocks.
- Page numbers should be retained when available.
- If structural extraction fails, the system may fall back to paragraph-style blocks, but only as a fallback mode.

## Phase-One Retrieval Pipeline

The phase-one pipeline should be:

1. parse query
2. recall candidate blocks from BM25
3. recall candidate blocks from vector search
4. fuse and deduplicate candidates
5. rerank block candidates
6. aggregate top blocks into ranked documents
7. emit structured evidence cards
8. build reader anchor payloads

This replaces the current behavior where the system retrieves plain chunks first and only later groups them into documents.

## Scoring And Reranking

Phase one should use three ranking stages.

### Stage 1: Broad Recall

Candidate generation should not attempt to be perfect.

Recommended pattern:

- BM25 top 40
- vector top 40
- deduplicate into roughly 50-70 candidates

### Stage 2: Block Reranking

Candidate blocks should then be reranked for actual relevance.

Preferred mechanism:

- cross-encoder reranker

Fallbacks:

- existing LLM rerank
- rules-based score fusion

Each block score should combine:

- reranker score
- BM25 score
- vector score
- exact phrase match boost
- heading match boost
- query coverage boost

### Stage 3: Document Aggregation

The primary ranking target returned to the workspace should still be the document.

Document score should combine:

- the best block score
- secondary evidence coverage reward
- diversity reward across heading paths
- deduplication penalty for redundant evidence from the same local area

This prevents one repetitive section from dominating the whole document ranking.

## Evidence Card Design

Each ranked document should return up to 3-5 evidence blocks, selected for diversity and usefulness.

Each evidence block should expose:

- `block_id`
- `block_type`
- `snippet`
- `heading_path`
- `page_number`
- `score`
- `match_reason`

`match_reason` should explain why the block was surfaced, such as:

- exact title match
- heading + body match
- clause-number match
- semantic reranker match

## Backend Design

### New Or Refactored Responsibilities

- `backend/utils/block_extractor.py`
  - parse Word/PDF into structured blocks
- `backend/app/services/indexing_service.py`
  - orchestrate block indexing into vector + BM25 + metadata stores
- `backend/utils/retriever.py`
  - become a retrieval adapter layer instead of a monolithic chunk-oriented utility
- `backend/app/services/retrieval_service.py`
  - orchestrate route selection and phase-one hybrid block retrieval
- `backend/app/services/document_service.py`
  - build reader payloads from structural blocks

### Phase-One Compatibility

The first phase should preserve the existing API entry points where possible:

- `POST /retrieval/workspace-search`
- `GET /documents/{id}/reader`

But the payloads should become structure-aware.

### Persistence Choices

Phase one should persist its new indexing state in the existing document metadata store rather than introducing a second metadata authority.

Recommended persistence split:

- document-level indexing status fields live in the existing document metadata JSON / storage layer
- block-level vector entries live in a dedicated Chroma collection for block retrieval
- block-level BM25 corpus lives in a dedicated block BM25 index/cache keyed by document and `index_version`

This avoids splitting document truth across multiple stores in the first phase.

## API Contract Changes

### `POST /retrieval/workspace-search`

Keep the route, but return structured evidence blocks rather than legacy chunk-shaped records.

The existing request field `mode` must keep its current meaning (`hybrid`, `keyword`, `vector`, `smart`).
The rollout switch must use a separate request field:

- `retrieval_version: "legacy" | "block"`

Phase-one behavior:

- if `retrieval_version` is omitted, treat the request as `retrieval_version=block`
- response must echo:
  - `retrieval_version_requested`
  - `retrieval_version_used`
- `mode` still controls recall style inside the selected retrieval version

Mixed-corpus rule for phase one:

- phase one does **not** merge legacy and block rankings inside one request
- the service chooses one primary pipeline per request
- if `retrieval_version=block` is requested but the required block index coverage is unavailable for the request, the whole request falls back to `legacy`
- that fallback must be explicit in `retrieval_version_used` and `meta.fallback_*`

This avoids score normalization problems between legacy chunks and structured blocks during phase one.

Phase-one meaning of `mode` under `retrieval_version=block`:

- `hybrid`: BM25 recall + vector recall + reranker
- `keyword`: BM25-only block recall, optional lightweight rules scoring, no vector dependency
- `vector`: vector-only block recall, optional reranker if configured
- `smart`: query expansion + hybrid block recall + reranker

Recommended phase-one candidate sizes:

- `hybrid`: BM25 top 40 + vector top 40
- `keyword`: BM25 top 50
- `vector`: vector top 50
- `smart`: per expanded query hybrid recall with capped merged candidate set before rerank

Top-level response shape should remain document-workspace compatible:

- `query`
- `mode`
- `retrieval_version_requested`
- `retrieval_version_used`
- `total_results`
- `total_documents`
- `results`
- `documents`
- `meta`
- `applied_filters`

Authoritative request schema:

```json
{
  "query": "string",
  "mode": "hybrid | keyword | vector | smart",
  "retrieval_version": "legacy | block",
  "limit": 10,
  "alpha": 0.5,
  "use_rerank": false,
  "use_query_expansion": true,
  "use_llm_rerank": true,
  "expansion_method": "llm",
  "file_types": [],
  "filename": null,
  "classification": null,
  "date_from": null,
  "date_to": null,
  "group_by_document": true
}
```

Each `documents[].evidence_blocks[]` should include:

- `block_id`
- `block_type`
- `snippet`
- `heading_path`
- `page_number`
- `score`
- `match_reason`

Each `documents[]` entry should still expose the existing document-centric fields used by the current frontend:

- `document_id`
- `filename`
- `file_type`
- `score`
- `hit_count`
- `best_block_id`
- `classification_result`
- `file_available`

Legacy fallback should be explicit in `meta`, for example:

- `meta.fallback_used`
- `meta.fallback_reason`
- `meta.fallback_documents`

### `POST /retrieval/workspace-search` Example

```json
{
  "query": "报销标准",
  "mode": "hybrid",
  "retrieval_version_requested": "block",
  "retrieval_version_used": "block",
  "total_results": 6,
  "total_documents": 2,
  "results": [],
  "documents": [
    {
      "document_id": "doc-1",
      "filename": "财务制度.docx",
      "file_type": ".docx",
      "score": 0.92,
      "hit_count": 3,
      "best_block_id": "doc-1:v2:14",
      "classification_result": "财务制度",
      "file_available": true,
      "evidence_blocks": [
        {
          "block_id": "doc-1:v2:14",
          "block_type": "paragraph",
          "snippet": "员工差旅报销标准如下……",
          "heading_path": ["第三章 财务管理", "3.2 报销标准"],
          "page_number": 12,
          "score": 0.92,
          "match_reason": "heading + body match"
        }
      ]
    }
  ],
  "meta": {
    "fallback_used": false
  },
  "applied_filters": {
    "file_types": [],
    "filename": null,
    "classification": null,
    "date_from": null,
    "date_to": null,
    "group_by_document": true
  }
}
```

### `GET /documents/{id}/reader`

Keep the route, but return structured reader blocks:

- `block_id`
- `block_index`
- `block_type`
- `heading_path`
- `page_number`
- `text`
- `matches[]`

This should allow the existing reader UI to become more informative without requiring a new page model in phase one.

The reader payload must preserve anchor behavior already used by the frontend:

- `best_anchor.block_id`
- `best_anchor.block_index`
- `best_anchor.match_index`

### `GET /documents/{id}/reader` Example

```json
{
  "document_id": "doc-1",
  "filename": "财务制度.docx",
  "file_type": ".docx",
  "query": "报销标准",
  "total_matches": 4,
  "best_anchor": {
    "block_id": "doc-1:v2:14",
    "block_index": 14,
    "match_index": 0,
    "start": 6,
    "end": 10,
    "term": "报销标准"
  },
  "blocks": [
    {
      "block_id": "doc-1:v2:14",
      "block_index": 14,
      "block_type": "paragraph",
      "heading_path": ["第三章 财务管理", "3.2 报销标准"],
      "page_number": 12,
      "text": "员工差旅报销标准如下……",
      "matches": [
        {
          "start": 6,
          "end": 10,
          "term": "报销标准"
        }
      ]
    }
  ]
}
```

## Frontend Compatibility

Phase one should preserve the current document workspace structure:

- `frontend/docagent-frontend/src/pages/SearchPage.vue`
- `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- `frontend/docagent-frontend/src/components/DocumentReader.vue`

The frontend changes should be additive:

- show heading path in result evidence
- show page number when available
- show block type when useful
- preserve existing document-first interaction model

The first phase should not redesign the workspace layout.

## Rollout Strategy

Phase one should run in parallel with the legacy retrieval path.

### Retrieval Versioning

Introduce an internal retrieval mode such as:

- `legacy`
- `block`

The system should be able to fall back to legacy retrieval if:

- block index is unavailable
- a document has not yet been re-indexed
- structural extraction failed badly

### Reindex Compatibility

Do not require a one-shot full corpus rebuild before rollout.

Each document should track:

- `index_version`
- `block_index_status`
- `block_count`
- `last_indexed_at`

These fields should be stored in the existing document metadata record returned by the storage layer.

Phase-one status values should be explicit:

- `block_index_status = not_indexed | indexing | ready | failed`

`vector indexed` and `block indexed` are not the same concept:

- existing `vector_indexed_documents` can continue to report legacy vector coverage
- phase one should add a distinct block-index coverage metric
- the stats API should eventually expose both numbers during migration

Recommended behavior:

- new uploads use the new block indexing path immediately
- old documents are backfilled asynchronously
- documents without the new index can temporarily use the legacy path

## Observability

The system should record at least:

- retrieval version used
- recall source of each winning block (`bm25`, `vector`, `reranker`)
- number of candidate blocks before and after rerank
- fallback-to-legacy rate
- index coverage rate for the corpus

These are necessary to judge whether the redesign is actually improving retrieval.

## Evaluation Strategy

The redesign must be evaluated by retrieval quality, not only by tests passing.

### Offline Regression Set

Build a benchmark set of roughly 20-50 Word/PDF questions covering:

- clause retrieval
- policy lookup
- heading / section localization
- synonym / paraphrase matching

### Quality Metrics

Track at least:

- document hit @1
- document hit @3
- best evidence block correctness
- reader anchor correctness

### Success Standard

Phase one is successful when:

1. Word/PDF queries default to the new block retrieval pipeline when indexed.
2. The system returns document-first results with structure-aware evidence.
3. The reader exposes heading path and page context where available.
4. Reranking is part of the decision path for final evidence ordering.
5. Offline retrieval quality is materially better than the current legacy pipeline.

## Risks

1. Structural extraction quality for PDF headings may be inconsistent across document styles.
2. Running BM25 + vector + reranker may increase latency if candidate sizes are not bounded carefully.
3. Maintaining legacy and new retrieval paths in parallel increases temporary complexity.
4. Reader payload compatibility may become messy if old paragraph-based assumptions remain in the frontend too long.

## Acceptance Criteria

1. The retrieval architecture is explicitly defined as a routed system, not a single chunk retriever.
2. Phase one is limited to Word/PDF clause retrieval improvements.
3. Phase one replaces naive chunk retrieval with structure-aware block retrieval for indexed Word/PDF documents.
4. `workspace-search` returns evidence blocks with structure metadata such as heading path and page number.
5. `document reader` payloads are based on structural blocks rather than raw plain-text chunk assumptions.
6. The design preserves compatibility with the current frontend workspace during phase one.
7. The rollout includes retrieval versioning and re-index compatibility for older documents.
8. The evaluation plan includes offline retrieval-quality benchmarking, not only unit or API tests.
