# Semantic Topic Tree Cluster + LLM Redesign

## Context

The current "semantic topic tree" is not semantic. It mixes two heuristics:

1. use `classification_result` when available
2. fall back to corpus keyword extraction when classification is missing

This produces labels that look like tags or frequent words rather than real business topics. It also means the tree quality is dominated by pre-existing classification data and token frequency, not by document-level semantic similarity.

The requested direction is to discard that logic and rebuild topic generation around:

1. document embeddings
2. unsupervised clustering
3. LLM-generated labels

## Goals

1. Replace keyword-driven topic generation with embedding-driven topic discovery.
2. Build a true two-level topic tree:
   - level 1: business-domain topic
   - level 2: concrete business-topic cluster
3. Generate node names with an LLM using representative cluster documents instead of token frequency.
4. Keep the existing API surface stable enough that the current frontend can adopt the new tree with limited changes.
5. Make rebuilds explicit and cache the generated tree artifact so the read path stays fast.

## Non-Goals

1. Preserve backward compatibility with keyword-based topic labels.
2. Support arbitrary tree depth in the first iteration.
3. Introduce a new background job system.
4. Guarantee perfectly stable labels across every rebuild.
5. Add HDBSCAN in the first iteration if the repository can avoid a new dependency.

## Product Decisions

### 1. Two-Level Tree Only

The first delivery should stop at two semantic levels. A deeper recursive tree would add parameter tuning and UI complexity before the quality of the first two levels is proven.

### 2. Offline Rebuild + Cached Read

`POST /api/v1/classification/topic-tree/build` is the expensive path. It may:

1. collect document vectors
2. run clustering
3. call the LLM for labels
4. persist the final artifact

`GET /api/v1/classification/topic-tree` should only return the latest valid artifact, or trigger a rebuild only when no valid artifact exists.

### 3. No Keyword Fallback For Naming

If the LLM is unavailable or returns unusable output, the rebuild should fail rather than silently regress to keyword labels. The system may continue serving the previous cached tree, but it should not present a new tree that came from the discarded approach.

### 4. K-Means First, Not HDBSCAN

The repository already includes `scikit-learn` and does not currently include `hdbscan`. The first version should therefore use `KMeans` with dynamic `k` selection rather than adding a new clustering dependency during the same behavior rewrite.

## Current-Code Constraints

### Backend

The current implementation lives in [backend/app/services/topic_tree_service.py](/home/zyq/DocAgentRAG/backend/app/services/topic_tree_service.py) and currently encodes the old strategy directly in the service.

The repository already has reusable building blocks:

1. Chroma-backed chunk storage in [backend/utils/storage.py](/home/zyq/DocAgentRAG/backend/utils/storage.py)
2. embedding helpers in [backend/utils/storage.py](/home/zyq/DocAgentRAG/backend/utils/storage.py)
3. LLM client utilities in [backend/utils/smart_retrieval.py](/home/zyq/DocAgentRAG/backend/utils/smart_retrieval.py)
4. artifact persistence in [backend/app/infra/metadata_store.py](/home/zyq/DocAgentRAG/backend/app/infra/metadata_store.py)

### Frontend

The current frontend consumes `topics` from [frontend/docagent-frontend/src/components/TopicTreePanel.vue](/home/zyq/DocAgentRAG/frontend/docagent-frontend/src/components/TopicTreePanel.vue), but only renders one expandable level today even though the schema already contains `children`.

There is also an API path mismatch in [frontend/docagent-frontend/src/api/index.js](/home/zyq/DocAgentRAG/frontend/docagent-frontend/src/api/index.js): the rebuild helper posts to `/classification/topic-tree/rebuild`, while the backend route is `/classification/topic-tree/build`.

## Proposed Architecture

### Overview

The new topic-tree generation flow should be:

1. collect document profiles
2. derive a document embedding for each document
3. cluster all documents into level-1 groups
4. cluster each level-1 group into level-2 groups
5. select representative documents per cluster
6. ask the LLM to name each cluster
7. persist the final two-level tree artifact

### Service Boundaries

Keep orchestration in [backend/app/services/topic_tree_service.py](/home/zyq/DocAgentRAG/backend/app/services/topic_tree_service.py), but move heavy sub-problems into focused helpers:

1. a clustering helper module for vector collection, `k` selection, K-Means execution, and representative-document selection
2. an LLM labeling helper module for prompt construction, JSON parsing, and output validation

This prevents `topic_tree_service.py` from remaining a monolith that mixes caching, vector math, prompt engineering, and response shaping.

## Data Flow

### 1. Build Document Profiles

For every document returned by `get_all_documents()`:

1. load `preview_content` and `full_content` metadata when available
2. load stored segments
3. build a compact semantic summary source containing:
   - filename
   - preview content
   - selected segment excerpts

This summary source is used for LLM representative payloads and for embedding fallback when chunk vectors are unavailable.

### 2. Derive Document Embeddings

Document vectors should come from the existing vector index first, not from keyword extraction.

Primary strategy:

1. read all chunk embeddings for a document from Chroma
2. L2-normalize chunk vectors
3. average them into one document vector
4. L2-normalize the result again

Fallback strategy:

1. if the document has no stored chunk vectors
2. embed the document summary source with the existing `embed_text` helper

Documents that still cannot produce a vector should be excluded from clustering and reported in rebuild metadata.

### 3. Level-1 Clustering

Run K-Means on all available document vectors.

`k` should not be hard-coded. The service should:

1. generate a candidate range based on corpus size
2. skip invalid candidate values
3. choose the `k` with the best silhouette score
4. fall back to `k=1` when the corpus is too small

The level-1 label should represent a business domain, not a specific transaction.

### 4. Level-2 Clustering

For each level-1 cluster:

1. cluster documents again inside the parent cluster
2. use a smaller candidate range than level 1
3. if the cluster is too small, keep a single level-2 child

The level-2 label should represent the concrete shared topic inside the parent domain.

### 5. Representative-Document Selection

Each cluster should select 3-5 representative documents by distance to the cluster centroid.

For each representative document, provide the LLM:

1. filename
2. short excerpt or preview
3. optionally the first meaningful segment excerpt

This keeps prompts focused on the center of the cluster instead of the noisiest edges.

### 6. LLM Labeling

The labeling helper should use separate prompts for each level.

Level-1 prompt:

1. ask for a business-domain label
2. maximum 8 Chinese characters
3. avoid generic words such as "文档", "资料", "业务", "管理"

Level-2 prompt:

1. ask for a concrete shared business topic
2. maximum 8 Chinese characters
3. avoid reusing the exact parent label

The model should be required to return strict JSON, for example:

```json
{"label":"年度审计","summary":"围绕年度财务审计材料与执行安排"}
```

If parsing fails, the rebuild should be treated as failed.

## Tree Shape

The persisted artifact should keep the existing top-level `topics` field, but the semantics change.

Top-level topics become level-1 semantic domains. Documents should only appear at level 2.

Target shape:

```json
{
  "schema_version": 2,
  "generation_method": "doc_embedding_cluster+llm_label",
  "generated_at": "2026-04-13T00:00:00",
  "total_documents": 42,
  "clustered_documents": 39,
  "excluded_documents": 3,
  "topic_count": 5,
  "topics": [
    {
      "topic_id": "topic-1",
      "label": "财务治理",
      "document_count": 12,
      "keywords": [],
      "documents": [],
      "children": [
        {
          "topic_id": "topic-1-1",
          "label": "年度审计",
          "document_count": 5,
          "documents": [
            {"document_id": "doc-1", "filename": "audit-plan.pdf"}
          ],
          "children": []
        }
      ]
    }
  ]
}
```

## Artifact Validity

The topic-tree artifact should be considered stale when any of the following is true:

1. `schema_version` is missing or less than `2`
2. `generation_method` is not `doc_embedding_cluster+llm_label`
3. `topics` contain leaf documents directly under level 1 without `children`

When stale, `GET` should trigger a rebuild only if no valid cached artifact exists. If a previous valid artifact exists, it should continue to be served until an explicit rebuild succeeds.

## Error Handling

### Rebuild Failure

If rebuild fails because:

1. no usable embeddings exist
2. LLM is unavailable
3. the LLM response cannot be parsed

then the API should:

1. return an error on rebuild
2. leave the previous valid artifact unchanged

### Sparse Corpus

For very small corpora:

1. 0 documents -> empty tree
2. 1 document -> one level-1 node, one level-2 child, one document
3. 2-3 documents -> conservative clustering, avoid forced fragmentation

## Frontend Implications

[frontend/docagent-frontend/src/components/TopicTreePanel.vue](/home/zyq/DocAgentRAG/frontend/docagent-frontend/src/components/TopicTreePanel.vue) should render two nested expandable levels:

1. level-1 topic card
2. level-2 topic rows inside the expanded parent
3. document chips inside the expanded level-2 node

The current page-level consumers in [frontend/docagent-frontend/src/pages/TaxonomyPage.vue](/home/zyq/DocAgentRAG/frontend/docagent-frontend/src/pages/TaxonomyPage.vue) and [frontend/docagent-frontend/src/pages/SearchPage.vue](/home/zyq/DocAgentRAG/frontend/docagent-frontend/src/pages/SearchPage.vue) should remain stable apart from consuming the richer tree shape.

## Testing Strategy

The redesign should be implemented test-first.

Required backend coverage:

1. old `classification_result` values no longer drive topic labels
2. documents are clustered into two levels and only appear once
3. representative-document payloads drive LLM labels into the saved artifact
4. stale old-format cache is invalidated
5. sparse corpus fallback behavior is deterministic

Required frontend coverage:

1. rebuild action hits the correct `/build` endpoint
2. two-level topic tree renders and expands correctly
3. document click behavior remains unchanged at the leaf level

## Rollout Notes

This redesign is intentionally an explicit semantic-tree rebuild, not an in-place tweak. The current keyword path should be removed from topic generation rather than retained as a hidden fallback, because retaining it would preserve the failure mode that motivated the rewrite.
