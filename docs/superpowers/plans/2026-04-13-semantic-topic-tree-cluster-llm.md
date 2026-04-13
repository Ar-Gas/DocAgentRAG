# Semantic Topic Tree Cluster + LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current keyword-driven semantic topic tree with a cached two-level tree generated from document embeddings, unsupervised clustering, and LLM-produced labels, while keeping the existing FastAPI and Vue feature entry points usable.

**Architecture:** Keep `TopicTreeService` as the orchestration boundary, but split vector clustering and LLM labeling into focused helpers. Build document vectors from stored chunk embeddings when possible, cluster documents with dynamic `KMeans`, label each cluster from representative documents through the existing LLM client, persist the result as a versioned artifact, and update the frontend to render the new two-level shape and call the correct rebuild endpoint.

**Tech Stack:** FastAPI, Pydantic, SQLite-backed metadata store, ChromaDB, existing embedding helpers, scikit-learn KMeans + silhouette score, Python pytest, Vue 3, Vite, Vitest, Vue Test Utils

---

## File Structure

### Backend

- Create: `backend/app/services/topic_clustering.py`
  - Build document vectors from stored embeddings, run dynamic `KMeans`, and select representative documents by centroid distance.
- Create: `backend/app/services/topic_labeler.py`
  - Build strict JSON prompts for level-1 and level-2 labels, call the existing LLM client, and validate parsed outputs.
- Modify: `backend/app/services/topic_tree_service.py`
  - Remove keyword/classification grouping, orchestrate clustering and labeling, invalidate stale cache artifacts, and shape the new two-level response.
- Modify: `backend/app/schemas/topic_tree.py`
  - Add `schema_version`, `clustered_documents`, `excluded_documents`, and lock the two-level tree response contract.
- Modify: `backend/utils/storage.py`
  - Add a helper that fetches per-document chunk embeddings and metadata from Chroma for topic clustering.
- Modify: `backend/test/test_topic_tree_service.py`
  - Replace old keyword/classification expectations with clustering/LLM/cache expectations.

### Frontend

- Modify: `frontend/docagent-frontend/src/api/index.js`
  - Fix the rebuild endpoint from `/classification/topic-tree/rebuild` to `/classification/topic-tree/build`.
- Modify: `frontend/docagent-frontend/src/components/TopicTreePanel.vue`
  - Render nested expandable level-1 and level-2 topics, with documents only at leaf nodes.
- Create: `frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js`
  - Lock two-level tree rendering, nested expansion, and leaf document click behavior.

### No Planned Changes

- `backend/api/classification.py`
  - Existing topic-tree endpoints already provide the correct read/build split.
- `backend/app/services/classification_service.py`
  - The service pass-through is sufficient once `TopicTreeService` changes.
- `frontend/docagent-frontend/src/pages/TaxonomyPage.vue`
  - Existing page-level state handling should remain valid after the nested tree panel update.

## Task 1: Lock The New Backend Contract With Failing Tests

**Files:**
- Modify: `backend/test/test_topic_tree_service.py`
- Test: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Rewrite the topic-tree service tests to describe the new behavior**

Add focused tests for:

```python
def test_build_topic_tree_uses_cluster_and_llm_labels_not_classification_results():
    tree = TopicTreeService().build_topic_tree(force_rebuild=True)
    assert tree["schema_version"] == 2
    assert tree["generation_method"] == "doc_embedding_cluster+llm_label"
    assert [topic["label"] for topic in tree["topics"]] == ["财务治理"]
    assert tree["topics"][0]["children"][0]["label"] == "年度审计"


def test_build_topic_tree_places_each_document_in_exactly_one_leaf():
    tree = TopicTreeService().build_topic_tree(force_rebuild=True)
    leaf_ids = [
        doc["document_id"]
        for topic in tree["topics"]
        for child in topic["children"]
        for doc in child["documents"]
    ]
    assert sorted(leaf_ids) == ["doc-1", "doc-2", "doc-3"]
    assert len(leaf_ids) == len(set(leaf_ids))


def test_get_topic_tree_ignores_legacy_cached_payload_and_rebuilds():
    rebuilt = TopicTreeService().get_topic_tree()
    assert rebuilt["schema_version"] == 2
```

- [ ] **Step 2: Run the targeted backend test file and verify it fails**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py -v`
Expected: FAIL because the current service still emits keyword/classification-based topics and does not produce the new schema.

- [ ] **Step 3: Commit the red test state once the failures are correct**

```bash
git add backend/test/test_topic_tree_service.py
git commit -m "test: lock semantic topic tree redesign contract"
```

## Task 2: Add Document-Vector Clustering Helpers

**Files:**
- Create: `backend/app/services/topic_clustering.py`
- Modify: `backend/utils/storage.py`
- Test: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Add one failing service-level test for missing chunk-embedding fallback**

Add a case that stubs:

1. stored chunk embeddings for `doc-1`
2. no stored chunk embeddings for `doc-2`
3. a fallback `embed_text` vector for `doc-2`

Expected result:

```python
assert tree["clustered_documents"] == 2
assert tree["excluded_documents"] == 0
```

- [ ] **Step 2: Run the single new backend test and verify it fails**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py::test_build_topic_tree_uses_summary_embedding_when_chunk_vectors_are_missing -v`
Expected: FAIL because no document-vector helper exists yet.

- [ ] **Step 3: Add the storage helper for chunk embeddings**

Implement a focused helper in `backend/utils/storage.py`:

```python
def list_document_chunk_embeddings(document_id: str) -> List[dict]:
    collection = get_chroma_collection()
    if collection is None:
        return []
    payload = collection.get(
        where={"document_id": document_id},
        include=["embeddings", "metadatas", "documents"],
    )
    return [
        {
            "embedding": embedding,
            "metadata": metadata or {},
            "content": content or "",
        }
        for embedding, metadata, content in zip(
            payload.get("embeddings") or [],
            payload.get("metadatas") or [],
            payload.get("documents") or [],
        )
        if embedding is not None
    ]
```

- [ ] **Step 4: Implement `topic_clustering.py` with minimal responsibilities**

Create helpers for:

1. document-vector derivation from chunk embeddings
2. fallback summary embedding with `embed_text`
3. dynamic `k` selection with `silhouette_score`
4. `KMeans` execution
5. centroid-distance representative ranking

Keep the public surface small, for example:

```python
def build_document_vectors(documents: List[dict]) -> Tuple[List[dict], List[dict]]:
    ...

def cluster_vectors(vectors: np.ndarray, level: int) -> List[int]:
    ...

def pick_representatives(documents: List[dict], center: np.ndarray, limit: int = 5) -> List[dict]:
    ...
```

- [ ] **Step 5: Re-run the targeted backend test and verify it passes**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py::test_build_topic_tree_uses_summary_embedding_when_chunk_vectors_are_missing -v`
Expected: PASS.

- [ ] **Step 6: Commit the clustering foundation**

```bash
git add backend/utils/storage.py \
  backend/app/services/topic_clustering.py \
  backend/test/test_topic_tree_service.py
git commit -m "feat: add document vector clustering helpers"
```

## Task 3: Add LLM Cluster Labeling Helpers

**Files:**
- Create: `backend/app/services/topic_labeler.py`
- Test: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Add a failing test for strict LLM label injection**

Describe a test where:

1. representative documents are predetermined
2. the LLM helper returns `{"label":"财务治理","summary":"..."}` for level 1
3. the LLM helper returns `{"label":"年度审计","summary":"..."}` for level 2

Expected result:

```python
assert tree["topics"][0]["label"] == "财务治理"
assert tree["topics"][0]["children"][0]["label"] == "年度审计"
```

- [ ] **Step 2: Run the single label-focused test and verify it fails**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py::test_build_topic_tree_uses_llm_labels_for_parent_and_child_topics -v`
Expected: FAIL because no LLM labeling module exists yet.

- [ ] **Step 3: Implement `topic_labeler.py`**

Use the existing LLM client from `backend/utils/smart_retrieval.py`, but wrap it with stricter behavior:

1. separate prompt builder for level 1 and level 2
2. strict JSON parsing
3. label length validation
4. rejection of generic labels such as `文档`, `资料`, `综合主题`, `业务管理`

Suggested shape:

```python
class TopicLabeler:
    def label_parent_topic(self, representatives: List[dict]) -> dict:
        ...

    def label_child_topic(self, parent_label: str, representatives: List[dict]) -> dict:
        ...
```

- [ ] **Step 4: Re-run the label-focused test**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py::test_build_topic_tree_uses_llm_labels_for_parent_and_child_topics -v`
Expected: PASS.

- [ ] **Step 5: Commit the LLM labeling helper**

```bash
git add backend/app/services/topic_labeler.py \
  backend/test/test_topic_tree_service.py
git commit -m "feat: add llm topic labeling helpers"
```

## Task 4: Replace TopicTreeService Orchestration And Cache Rules

**Files:**
- Modify: `backend/app/services/topic_tree_service.py`
- Modify: `backend/app/schemas/topic_tree.py`
- Test: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Add a failing test for stale-cache invalidation**

Describe a cached payload like:

```python
legacy_cache = {
    "generated_at": "2026-04-13T00:00:00",
    "generation_method": "classification_result+corpus_keywords",
    "topics": [{"topic_id": "topic-1", "label": "财务", "documents": []}],
}
```

Expected result:

```python
tree = TopicTreeService().get_topic_tree()
assert tree["generation_method"] == "doc_embedding_cluster+llm_label"
assert tree["schema_version"] == 2
```

- [ ] **Step 2: Run the stale-cache test and verify it fails**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py::test_get_topic_tree_ignores_legacy_cached_payload_and_rebuilds -v`
Expected: FAIL because legacy artifacts are currently accepted as-is.

- [ ] **Step 3: Replace the service orchestration**

Update `TopicTreeService` to:

1. reject old artifacts with `_is_valid_topic_tree_artifact`
2. build document profiles without using `classification_result` as a grouping input
3. call `TopicClustering` for level-1 and level-2 clustering
4. call `TopicLabeler` for parent and child labels
5. attach documents only to child topics
6. emit:
   - `schema_version`
   - `clustered_documents`
   - `excluded_documents`
   - `generation_method = "doc_embedding_cluster+llm_label"`

- [ ] **Step 4: Update the schema models**

Adjust `backend/app/schemas/topic_tree.py` so the response contract matches the new artifact fields and still supports `children`.

- [ ] **Step 5: Re-run the full backend topic-tree test file**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit the service rewrite**

```bash
git add backend/app/services/topic_tree_service.py \
  backend/app/schemas/topic_tree.py \
  backend/test/test_topic_tree_service.py
git commit -m "feat: rebuild topic tree from clusters and llm labels"
```

## Task 5: Fix The Frontend API Contract And Render A Real Two-Level Tree

**Files:**
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/components/TopicTreePanel.vue`
- Create: `frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js`

- [ ] **Step 1: Add a failing component test for nested topic rendering**

Create a test such as:

```javascript
it('renders parent topics, child topics, and emits leaf document selection', async () => {
  const tree = {
    total_documents: 2,
    topics: [
      {
        topic_id: 'topic-1',
        label: '财务治理',
        document_count: 2,
        children: [
          {
            topic_id: 'topic-1-1',
            label: '年度审计',
            document_count: 2,
            documents: [
              { document_id: 'doc-1', filename: 'audit-plan.pdf', file_type: '.pdf' },
            ],
          },
        ],
      },
    ],
  }
})
```

Assert:

1. parent label is visible
2. expanding the parent reveals the child label
3. expanding the child reveals the document button
4. clicking the button emits `select-document`

- [ ] **Step 2: Run the new frontend component test and verify it fails**

Run: `cd frontend/docagent-frontend && npm run test -- src/components/__tests__/TopicTreePanel.spec.js`
Expected: FAIL because the current panel only renders one level.

- [ ] **Step 3: Fix the rebuild API helper**

Change:

```javascript
buildTopicTree: (forceRebuild = false) => {
  return request.post('/classification/topic-tree/build', { force_rebuild: forceRebuild })
}
```

- [ ] **Step 4: Update the tree panel for two nested expansion states**

Implement separate expansion tracking for:

1. level-1 topics
2. level-2 topics

Render documents only under level-2 nodes. Preserve the existing `select-document` event signature.

- [ ] **Step 5: Re-run the component test**

Run: `cd frontend/docagent-frontend && npm run test -- src/components/__tests__/TopicTreePanel.spec.js`
Expected: PASS.

- [ ] **Step 6: Commit the frontend tree update**

```bash
git add frontend/docagent-frontend/src/api/index.js \
  frontend/docagent-frontend/src/components/TopicTreePanel.vue \
  frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js
git commit -m "feat: render two-level semantic topic tree"
```

## Task 6: Run Verification Before Claiming Completion

**Files:**
- Test: `backend/test/test_topic_tree_service.py`
- Test: `frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js`
- Test: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`

- [ ] **Step 1: Run backend topic-tree coverage**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py -v`
Expected: PASS.

- [ ] **Step 2: Run frontend topic-tree coverage**

Run: `cd frontend/docagent-frontend && npm run test -- src/components/__tests__/TopicTreePanel.spec.js src/pages/__tests__/SearchPage.spec.js`
Expected: PASS.

- [ ] **Step 3: Run one targeted smoke check of the build path**

Run: `cd backend && python3 -m pytest test/test_topic_tree_service.py::test_get_topic_tree_ignores_legacy_cached_payload_and_rebuilds -v`
Expected: PASS.

- [ ] **Step 4: Commit the verified end state**

```bash
git add backend/test/test_topic_tree_service.py \
  frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js \
  frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js
git commit -m "test: verify semantic topic tree redesign"
```

## Notes For Execution

1. Do not reintroduce keyword extraction as a silent fallback for cluster labels.
2. Do not attach documents directly under level-1 topics in the new artifact.
3. Preserve the current endpoint names; only fix the incorrect frontend rebuild path.
4. Keep commits focused by task; the repository is already dirty, so stage only the files owned by each step.
