# Document-Centric Search Redesign

## Context

The current search workspace mixes four different concerns in one screen: retrieval, preview, summary, and classification tables. The UI exposes chunk-level retrieval as a user concept, while the backend still treats chunks as both retrieval evidence and display objects. This produces repeated panels, weak semantics, and a poor reading flow.

The current classification tree is also not genuinely intelligent. It is a fixed template of content category, file type, and time bucket. It does not infer new topic structure from the current document corpus.

## Goals

1. Make the primary object in search the document, not the chunk.
2. Replace chunk preview with a text reader that behaves like `Ctrl+F`: highlight all hits, jump between hits, and anchor on the best match.
3. Change retrieval summaries from “summarize top chunks” to “summarize top documents with evidence.”
4. Replace the template classification tree with a dynamic semantic topic tree generated from the current corpus.
5. Reduce duplicated UI regions and make each panel have one clear responsibility.

## Non-Goals

1. Native Office rendering in the browser is not the primary goal in this phase.
2. Visual PDF annotation is not required for the first redesign pass.
3. Long-term dual maintenance of old and new search models is explicitly out of scope.

## Product Model

The new workspace is document-centric:

- Search still recalls chunks internally.
- The API returns ranked documents with chunk evidence attached.
- The result list shows documents only.
- The reader opens extracted document text and uses evidence anchors to jump to matching blocks.
- Summary and classification generation operate on document evidence cards, not raw chunk arrays.

Chunks remain an internal retrieval primitive. They are not a primary UI object.

## User Experience

The workspace becomes a three-column layout:

### Left: Search And Topic Navigation

- Query input, mode, filters, and sorting.
- Dynamic semantic topic tree for browsing the current corpus.
- Search status metrics: total documents, vector indexed documents, segment documents.

### Center: Document Results

Each row represents one document:

- filename
- file type
- dynamic topic labels
- best score
- hit count
- best excerpt with keyword highlighting
- optional metadata such as time and parser status

There is no user-facing “group by chunk” mode.

### Right: Document Reader

The reader is extracted-text-first:

- full document text shown as blocks
- all query hits highlighted
- “previous hit / next hit”
- auto-scroll to best match on open
- evidence rail showing matched blocks
- toggles for “full text” and “matched blocks only”

This replaces the current preview card plus chunk list model.

## Backend Design

### Retrieval Response Model

`POST /retrieval/workspace-search` should return:

- `documents[]`: ranked document results
- `meta`: retrieval metadata
- `applied_filters`

Each document result should contain:

- `document_id`
- `filename`
- `file_type`
- `score`
- `hit_count`
- `best_excerpt`
- `matched_terms[]`
- `best_block_id`
- `evidence_blocks[]`

`evidence_blocks[]` contains the matched chunk or block references used for ranking and navigation. It is not the main display model.

### Reader API

Add a dedicated reader endpoint:

- `GET /documents/{id}/reader?query=...`

It should return:

- `blocks[]`
- `match_ranges[]`
- `best_match_block_id`
- `match_count`
- `document metadata`

This endpoint is responsible for turning retrieval evidence into reader navigation data.

### Summary Pipeline

Current state: the summary path only includes top result snippets.

New pipeline:

1. retrieve chunk evidence
2. aggregate by document
3. build one evidence card per document
4. send top `N` document evidence cards to the LLM
5. return summary plus document-level citations and block-level anchors

The LLM should summarize documents, not chunks.

### Dynamic Topic Tree

Replace the template tree with a corpus-driven semantic tree:

1. build document-level semantic representations from title, summary, keywords, and representative blocks
2. generate embeddings
3. run hierarchical clustering over the current corpus
4. name each node with keywords or an LLM label
5. persist a tree that includes node summary, representative documents, and children

The output should be a semantic map of the current corpus, not a predefined folder taxonomy.

## Frontend Design

The current search page should be decomposed into focused units:

- `SearchToolbar`
- `TopicTreePanel`
- `DocumentResultList`
- `DocumentReader`
- `SummaryDrawer` or `SummaryPanel`
- `ClassificationReportDrawer`

The following existing components should be replaced or retired:

- `SearchResultsTable.vue`
- `DocumentPreviewPanel.vue`
- `ClassificationTablePanel.vue`

`SearchPage.vue` should become an orchestrator, not a dense stateful page containing every behavior inline.

## Migration Strategy

### Step 1

Refactor backend contracts first:

- document-centric search payload
- reader endpoint
- document-based summary input
- dynamic topic tree API

### Step 2

Switch the frontend workspace to the new document model.

### Step 3

Delete obsolete chunk-first UI and old default classification tree usage.

## Compatibility

Short transition compatibility is acceptable:

- old search fields may be kept temporarily in the response
- old classification tree endpoint may remain as `legacy`

Long-term coexistence is not acceptable. The redesign should end with one canonical user model: documents.

## Risks

1. Many stored documents currently have no vector chunks. The redesign must still work via metadata and extracted-text fallback.
2. Extracted text quality varies across file formats. Reader behavior must tolerate missing structure.
3. Topic clustering quality will depend on document text quality and embedding quality.

## Testing Strategy

1. Retrieval service tests for document aggregation and evidence selection.
2. Reader API tests for hit highlighting and best-match anchoring.
3. Summary tests that verify document-level citation structure.
4. Topic tree tests that verify dynamic clustering output shape and naming fallback.
5. Frontend component tests for result selection, reader jump navigation, and highlighted matches.
6. End-to-end tests for the full flow: search -> open document -> jump matches -> summarize -> browse topic tree.

## Acceptance Criteria

1. Search results show documents only.
2. Opening a result jumps the reader to the best hit and highlights all hits.
3. The summary endpoint uses document evidence cards instead of raw chunk lists.
4. The topic tree is generated from the current corpus and is not hard-coded to fixed taxonomy buckets.
5. The old chunk-first result mode is removed from the default experience.
