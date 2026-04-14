# Document-Centric Search Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild search, reading, summarization, and taxonomy around documents instead of chunks so the web workspace behaves like a document search tool rather than a chunk debugger.

**Architecture:** Keep FastAPI + SQLite metadata + Chroma retrieval as the base, but move the public workspace contract to document-centric payloads with chunk evidence attached. Add a reader API that translates matched evidence into highlightable text blocks, shift LLM summarization and classification reports to document evidence cards, and replace the fixed multi-level taxonomy with a dynamic semantic topic tree generated from the current corpus.

**Tech Stack:** FastAPI, SQLite metadata store, ChromaDB, Vue 3, Element Plus, Axios, pytest, Vitest, Vue Test Utils

---

## File Structure

### Backend

- Create: `backend/app/schemas/retrieval_workspace.py`
  - Pydantic models for document-centric workspace search, evidence blocks, summary requests, and topic tree payloads.
- Create: `backend/app/schemas/document_reader.py`
  - Models for reader blocks, match ranges, best-match anchors, and reader metadata.
- Create: `backend/app/schemas/topic_tree.py`
  - Models for semantic topic nodes, topic documents, and rebuild responses.
- Create: `backend/app/services/topic_tree_service.py`
  - Corpus-driven semantic tree generation and persistence orchestration.
- Modify: `backend/app/services/retrieval_service.py`
  - Aggregate chunk recall into document results, build evidence cards, and call the new summary pipeline.
- Modify: `backend/app/services/document_service.py`
  - Add the reader payload builder and expose block/match level document reading.
- Modify: `backend/app/services/classification_service.py`
  - Move “classification table” generation onto document evidence cards and bridge to the new topic tree service.
- Modify: `backend/api/retrieval.py`
  - Change workspace request/response shape and summary endpoint contract.
- Modify: `backend/api/document.py`
  - Add a document reader endpoint.
- Modify: `backend/api/classification.py`
  - Add topic tree endpoints and mark legacy multi-level tree endpoints as compatibility paths.
- Modify: `backend/utils/smart_retrieval.py`
  - Replace chunk-only summary and classification-table prompts with document-evidence prompts.
- Modify: `backend/utils/retriever.py`
  - Preserve chunk retrieval internally but expose document aggregation helpers and vector index stats.
- Modify: `backend/utils/multi_level_classifier.py`
  - Freeze as legacy-only entry point until deleted after migration.
- Test: `backend/test/test_retrieval_service_api.py`
- Test: `backend/test/test_classification_tables.py`
- Create: `backend/test/test_document_reader_api.py`
- Create: `backend/test/test_topic_tree_service.py`

### Frontend

- Modify: `frontend/docagent-frontend/src/api/index.js`
  - Replace chunk-first workspace calls with document-centric search, reader, summary, and topic-tree APIs.
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
  - Reduce the page to orchestration and layout only.
- Modify: `frontend/docagent-frontend/src/pages/TaxonomyPage.vue`
  - Reuse the new topic tree panel instead of the legacy multi-level classification manager.
- Create: `frontend/docagent-frontend/src/components/SearchToolbar.vue`
  - Query input, search mode, filters, and rebuild actions.
- Create: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
  - Document-only result list with keyword-highlighted best excerpt.
- Create: `frontend/docagent-frontend/src/components/DocumentReader.vue`
  - Extracted-text reader with hit highlighting and jump navigation.
- Create: `frontend/docagent-frontend/src/components/TopicTreePanel.vue`
  - Dynamic semantic topic tree browser.
- Create: `frontend/docagent-frontend/src/components/SummaryDrawer.vue`
  - LLM summary with document-level citations.
- Create: `frontend/docagent-frontend/src/components/ClassificationReportDrawer.vue`
  - On-demand classification report instead of a permanent main-panel widget.
- Modify: `frontend/docagent-frontend/src/App.vue`
  - Update navigation labels and page framing text.
- Modify: `frontend/docagent-frontend/src/assets/styles/global.scss`
  - Normalize shared layout tokens for the new document-centric workspace.
- Modify: `frontend/docagent-frontend/package.json`
  - Add a frontend test command.
- Create: `frontend/docagent-frontend/vitest.config.js`
- Create: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`
- Create: `frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js`

### Legacy Files To Retire At The End

- Delete: `frontend/docagent-frontend/src/components/SearchResultsTable.vue`
- Delete: `frontend/docagent-frontend/src/components/DocumentPreviewPanel.vue`
- Delete: `frontend/docagent-frontend/src/components/ClassificationTablePanel.vue`
- Delete or legacy-freeze: `frontend/docagent-frontend/src/components/MultiLevelClassification.vue`

---

### Task 1: Define The Document-Centric Workspace Contract

**Files:**
- Create: `backend/app/schemas/retrieval_workspace.py`
- Modify: `backend/api/retrieval.py`
- Modify: `backend/app/services/retrieval_service.py`
- Test: `backend/test/test_retrieval_service_api.py`

- [ ] **Step 1: Write the failing test for document-centric workspace payload**

```python
def test_workspace_search_returns_document_results_with_evidence(monkeypatch):
    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda *args, **kwargs: [
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "path": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.92,
                "content_snippet": "预算审批流程和采购说明",
                "chunk_index": 2,
            },
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "path": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.81,
                "content_snippet": "预算执行和报销约束",
                "chunk_index": 5,
            },
        ],
    )
    monkeypatch.setattr(retrieval_service_module, "get_document_info", lambda document_id: {
        "id": document_id,
        "filename": "budget-report.pdf",
        "file_type": ".pdf",
        "classification_result": "财务制度",
        "created_at_iso": "2026-03-20T10:00:00",
    })
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", lambda document_id: {
        "document_id": document_id,
        "preview_content": "预算审批流程和采购说明",
    })
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])

    payload = RetrievalService().workspace_search(query="预算 审批", mode="hybrid", limit=10)

    assert payload["documents"][0]["document_id"] == "doc-1"
    assert payload["documents"][0]["hit_count"] == 2
    assert payload["documents"][0]["best_excerpt"] == "预算审批流程和采购说明"
    assert payload["documents"][0]["best_block_id"] == "doc-1#2"
    assert payload["documents"][0]["evidence_blocks"][0]["block_index"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test/test_retrieval_service_api.py::test_workspace_search_returns_document_results_with_evidence -v`
Expected: FAIL because `workspace_search()` does not yet expose `hit_count`, `best_excerpt`, `best_block_id`, or `evidence_blocks`.

- [ ] **Step 3: Write the minimal schema models**

```python
# backend/app/schemas/retrieval_workspace.py
from pydantic import BaseModel


class EvidenceBlock(BaseModel):
    block_id: str
    block_index: int
    snippet: str
    score: float


class DocumentSearchResult(BaseModel):
    document_id: str
    filename: str
    file_type: str
    score: float
    hit_count: int
    best_excerpt: str
    matched_terms: list[str] = []
    best_block_id: str | None = None
    evidence_blocks: list[EvidenceBlock] = []
```

- [ ] **Step 4: Implement document aggregation in the retrieval service**

```python
def _aggregate_workspace_results(self, raw_results: list[dict]) -> list[dict]:
    grouped = {}
    for item in raw_results:
        document_id = item["document_id"]
        group = grouped.setdefault(document_id, {
            "document_id": document_id,
            "filename": item.get("filename", ""),
            "file_type": item.get("file_type", ""),
            "score": 0.0,
            "hit_count": 0,
            "best_excerpt": "",
            "matched_terms": [],
            "best_block_id": None,
            "evidence_blocks": [],
        })
        group["hit_count"] += 1
        group["score"] = max(group["score"], item.get("similarity", 0.0))
        block_index = item.get("chunk_index", 0)
        evidence = {
            "block_id": f"{document_id}#{block_index}",
            "block_index": block_index,
            "snippet": item.get("content_snippet", ""),
            "score": item.get("similarity", 0.0),
        }
        group["evidence_blocks"].append(evidence)
        if group["best_block_id"] is None or evidence["score"] >= group["score"]:
            group["best_block_id"] = evidence["block_id"]
            group["best_excerpt"] = evidence["snippet"]
    return sorted(grouped.values(), key=lambda item: item["score"], reverse=True)
```

- [ ] **Step 5: Wire the API route to return document-centric payloads**

Run the route through `WorkspaceSearchRequest` but drop the UI-facing `group_by_document` behavior from the response contract. Keep `results` only as a temporary compatibility field until Task 7 removes it.

- [ ] **Step 6: Run the targeted tests**

Run: `pytest backend/test/test_retrieval_service_api.py -k "workspace_search" -v`
Expected: PASS for both legacy compatibility checks and the new document-centric response shape.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/retrieval_workspace.py \
  backend/api/retrieval.py \
  backend/app/services/retrieval_service.py \
  backend/test/test_retrieval_service_api.py
git commit -m "feat: add document-centric workspace search contract"
```

### Task 2: Add The Reader API And Text Highlight Navigation

**Files:**
- Create: `backend/app/schemas/document_reader.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/api/document.py`
- Test: `backend/test/test_document_reader_api.py`

- [ ] **Step 1: Write the failing reader service test**

```python
def test_get_document_reader_marks_all_query_hits(monkeypatch):
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: {
        "id": document_id,
        "filename": "budget-report.pdf",
        "file_type": ".pdf",
    })
    monkeypatch.setattr(document_service_module, "get_document_content_record", lambda document_id: {
        "document_id": document_id,
        "full_content": "预算审批流程\\n采购申请\\n预算执行复核",
        "preview_content": "预算审批流程",
    })
    monkeypatch.setattr(document_service_module, "list_document_segments", lambda document_id: [
        {"segment_id": "doc-1#0", "segment_index": 0, "content": "预算审批流程"},
        {"segment_id": "doc-1#1", "segment_index": 1, "content": "采购申请"},
        {"segment_id": "doc-1#2", "segment_index": 2, "content": "预算执行复核"},
    ])

    payload = DocumentService().get_document_reader("doc-1", query="预算")

    assert payload["best_match_block_id"] == "doc-1#0"
    assert payload["match_count"] == 2
    assert payload["blocks"][0]["matches"][0]["text"] == "预算"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test/test_document_reader_api.py::test_get_document_reader_marks_all_query_hits -v`
Expected: FAIL because `DocumentService` does not yet expose `get_document_reader()`.

- [ ] **Step 3: Add the reader models**

```python
# backend/app/schemas/document_reader.py
class MatchRange(BaseModel):
    start: int
    end: int
    text: str


class ReaderBlock(BaseModel):
    block_id: str
    block_index: int
    content: str
    matches: list[MatchRange] = []
```

- [ ] **Step 4: Implement the reader payload builder**

```python
def get_document_reader(self, document_id: str, query: str = "") -> Dict:
    doc_info = self.get_document(document_id)
    content_record = get_document_content_record(document_id) or {}
    segments = list_document_segments(document_id)
    blocks = []
    best_match_block_id = None
    match_count = 0

    for index, segment in enumerate(segments):
        content = segment.get("content", "")
        matches = self._find_matches(content, query)
        if matches and best_match_block_id is None:
            best_match_block_id = segment.get("segment_id") or f"{document_id}#{index}"
        match_count += len(matches)
        blocks.append({
            "block_id": segment.get("segment_id") or f"{document_id}#{index}",
            "block_index": segment.get("segment_index", index),
            "content": content,
            "matches": matches,
        })
    return {
        **doc_info,
        "full_content": content_record.get("full_content", ""),
        "blocks": blocks,
        "best_match_block_id": best_match_block_id,
        "match_count": match_count,
    }
```

- [ ] **Step 5: Add the new document route**

```python
@router.get("/{document_id}/reader", summary="获取文档阅读器数据")
async def get_document_reader(document_id: str, query: str = Query(default="")):
    return success(data=document_service.get_document_reader(document_id, query))
```

- [ ] **Step 6: Run the reader tests**

Run: `pytest backend/test/test_document_reader_api.py -v`
Expected: PASS with highlighted matches and best-block anchoring.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/document_reader.py \
  backend/app/services/document_service.py \
  backend/api/document.py \
  backend/test/test_document_reader_api.py
git commit -m "feat: add document reader API with hit navigation"
```

### Task 3: Move Summary And Classification Reports To Document Evidence Cards

**Files:**
- Modify: `backend/utils/smart_retrieval.py`
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/api/retrieval.py`
- Modify: `backend/api/classification.py`
- Test: `backend/test/test_classification_tables.py`
- Test: `backend/test/test_retrieval_service_api.py`

- [ ] **Step 1: Write the failing summary pipeline test**

```python
def test_summarize_results_uses_document_evidence_cards(monkeypatch):
    captured = {}

    def fake_summary(query, documents, max_items=6):
        captured["query"] = query
        captured["documents"] = documents
        return {"summary": "汇总完成", "citations": [], "llm_used": False}

    monkeypatch.setattr(retrieval_service_module, "summarize_retrieval_results", fake_summary)

    payload = RetrievalService().summarize_results(
        "预算",
        [
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "best_excerpt": "预算审批流程",
                "evidence_blocks": [{"block_id": "doc-1#2", "snippet": "预算审批流程"}],
            }
        ],
    )

    assert payload["summary"] == "汇总完成"
    assert captured["documents"][0]["document_id"] == "doc-1"
    assert captured["documents"][0]["evidence_blocks"][0]["block_id"] == "doc-1#2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test/test_retrieval_service_api.py::test_summarize_results_uses_document_evidence_cards -v`
Expected: FAIL because the summary path still forwards a raw chunk-like `results` array.

- [ ] **Step 3: Change the summary helper signature**

```python
def summarize_retrieval_results(query: str, documents: list[dict], max_items: int = 6) -> dict:
    trimmed_documents = documents[:max_items]
    docs_text = []
    for index, item in enumerate(trimmed_documents, start=1):
        evidence_lines = [
            f"- 证据块 {block['block_id']}: {block['snippet'][:200]}"
            for block in item.get("evidence_blocks", [])[:3]
        ]
        docs_text.append(
            "\n".join([
                f"[文档{index}] 文件名: {item.get('filename', '未知文件')}",
                f"命中次数: {item.get('hit_count', 0)}",
                f"最佳摘要: {item.get('best_excerpt', '')}",
                *evidence_lines,
            ])
        )
```

- [ ] **Step 4: Update classification report generation to consume documents**

```python
def generate_classification_table(self, query: str, documents: List[Dict], persist: bool = True) -> Dict:
    if not documents:
        raise AppServiceError(3002, "检索结果为空，无法生成分类表")
    enriched = [
        {
            **item,
            "document_category": (get_document_info(item["document_id"]) or {}).get("classification_result"),
            "best_excerpt": item.get("best_excerpt", ""),
        }
        for item in documents
    ]
    table = generate_classification_table(query, enriched)
```

- [ ] **Step 5: Update request models and routes**

Change summary and classification-report inputs from `results: List[Dict[str, Any]]` to `documents: List[Dict[str, Any]]`, and keep a short compatibility shim only if the frontend transition requires one release of overlap.

- [ ] **Step 6: Run the targeted tests**

Run: `pytest backend/test/test_retrieval_service_api.py backend/test/test_classification_tables.py -v`
Expected: PASS with document-level summary and classification-report payloads.

- [ ] **Step 7: Commit**

```bash
git add backend/utils/smart_retrieval.py \
  backend/app/services/retrieval_service.py \
  backend/app/services/classification_service.py \
  backend/api/retrieval.py \
  backend/api/classification.py \
  backend/test/test_retrieval_service_api.py \
  backend/test/test_classification_tables.py
git commit -m "feat: summarize and classify search results by document evidence"
```

### Task 4: Build The Dynamic Semantic Topic Tree Backend

**Files:**
- Create: `backend/app/schemas/topic_tree.py`
- Create: `backend/app/services/topic_tree_service.py`
- Modify: `backend/api/classification.py`
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/utils/multi_level_classifier.py`
- Create: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Write the failing topic-tree clustering test**

```python
def test_build_topic_tree_groups_documents_by_semantic_similarity(monkeypatch):
    monkeypatch.setattr(topic_tree_module, "get_all_documents", lambda: [
        {"id": "doc-1", "filename": "预算制度.pdf", "preview_content": "预算审批 财务 报销"},
        {"id": "doc-2", "filename": "采购规范.pdf", "preview_content": "采购 流程 供应商"},
        {"id": "doc-3", "filename": "招聘手册.docx", "preview_content": "招聘 面试 入职"},
    ])
    monkeypatch.setattr(topic_tree_module.TopicTreeService, "_embed_documents", lambda self, docs: [
        [1.0, 0.0],
        [0.9, 0.1],
        [0.0, 1.0],
    ])

    tree = TopicTreeService().build_topic_tree()

    assert tree["total_documents"] == 3
    assert len(tree["nodes"]) >= 2
    assert any(node["document_count"] == 2 for node in tree["nodes"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test/test_topic_tree_service.py::test_build_topic_tree_groups_documents_by_semantic_similarity -v`
Expected: FAIL because `TopicTreeService` does not exist yet.

- [ ] **Step 3: Create the topic tree service**

```python
class TopicTreeService:
    def build_topic_tree(self, use_llm_labels: bool = True) -> Dict[str, Any]:
        documents = self._load_topic_documents()
        if not documents:
            return {"generated_at": datetime.now().isoformat(), "total_documents": 0, "nodes": []}
        vectors = self._embed_documents(documents)
        clusters = self._cluster_documents(vectors)
        return self._build_tree_payload(documents, clusters, use_llm_labels=use_llm_labels)
```

- [ ] **Step 4: Add the new classification routes**

```python
@router.post("/topic-tree/rebuild", summary="重建动态语义主题树")
async def rebuild_topic_tree():
    return success(data=classification_service.rebuild_topic_tree())


@router.get("/topic-tree", summary="获取动态语义主题树")
async def get_topic_tree():
    return success(data=classification_service.get_topic_tree())
```

- [ ] **Step 5: Freeze the old tree as legacy-only**

Keep `/classification/multi-level/*` available during migration, but rename the page label and route usage in the frontend so the old tree is no longer the primary entry point.

- [ ] **Step 6: Run the topic tree tests**

Run: `pytest backend/test/test_topic_tree_service.py -v`
Expected: PASS with deterministic clustering output and fallback node naming.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/topic_tree.py \
  backend/app/services/topic_tree_service.py \
  backend/api/classification.py \
  backend/app/services/classification_service.py \
  backend/utils/multi_level_classifier.py \
  backend/test/test_topic_tree_service.py
git commit -m "feat: add dynamic semantic topic tree backend"
```

### Task 5: Refactor The Search Workspace Into Focused Components

**Files:**
- Create: `frontend/docagent-frontend/src/components/SearchToolbar.vue`
- Create: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- Create: `frontend/docagent-frontend/src/components/DocumentReader.vue`
- Create: `frontend/docagent-frontend/src/components/TopicTreePanel.vue`
- Create: `frontend/docagent-frontend/src/components/SummaryDrawer.vue`
- Create: `frontend/docagent-frontend/src/components/ClassificationReportDrawer.vue`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/assets/styles/global.scss`
- Modify: `frontend/docagent-frontend/src/App.vue`

- [ ] **Step 1: Add a failing frontend component test for document results**

```javascript
import { mount } from '@vue/test-utils'
import DocumentResultList from '../DocumentResultList.vue'

test('renders document hit count and best excerpt', () => {
  const wrapper = mount(DocumentResultList, {
    props: {
      loading: false,
      documents: [
        {
          document_id: 'doc-1',
          filename: 'budget-report.pdf',
          hit_count: 3,
          best_excerpt: '预算审批流程',
          matched_terms: ['预算'],
          score: 0.92,
        },
      ],
      selectedDocumentId: 'doc-1',
    },
  })

  expect(wrapper.text()).toContain('budget-report.pdf')
  expect(wrapper.text()).toContain('3')
  expect(wrapper.text()).toContain('预算审批流程')
})
```

- [ ] **Step 2: Run the frontend test to verify it fails**

Run: `cd frontend/docagent-frontend && npm run test -- --run src/components/__tests__/DocumentResultList.spec.js`
Expected: FAIL because the new component and test command do not yet exist.

- [ ] **Step 3: Add the frontend test harness**

```json
{
  "scripts": {
    "build": "vite build",
    "test": "vitest run"
  },
  "devDependencies": {
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^26.1.0",
    "vitest": "^3.2.4"
  }
}
```

- [ ] **Step 4: Build the new search components**

```vue
<!-- DocumentResultList.vue -->
<template>
  <section class="result-list">
    <button
      v-for="doc in documents"
      :key="doc.document_id"
      class="result-row"
      :class="{ selected: doc.document_id === selectedDocumentId }"
      @click="$emit('select-document', doc.document_id)"
    >
      <strong>{{ doc.filename }}</strong>
      <span>{{ doc.hit_count }} 命中</span>
      <p v-html="doc.best_excerpt_html || doc.best_excerpt" />
    </button>
  </section>
</template>
```

- [ ] **Step 5: Simplify `SearchPage.vue` to orchestration only**

The page should only:
- own the query/filter state
- request `workspaceSearch`
- request `getDocumentReader`
- request `summarizeResults`
- request `getTopicTree`
- coordinate component selection state

Remove:
- permanent classification table side panel
- `group_by_document` UI toggle
- the old preview/chunk card workflow

- [ ] **Step 6: Run the frontend tests and build**

Run:
- `cd frontend/docagent-frontend && npm run test -- --run`
- `cd frontend/docagent-frontend && npm run build`

Expected:
- tests PASS
- build PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/docagent-frontend/package.json \
  frontend/docagent-frontend/vitest.config.js \
  frontend/docagent-frontend/src/api/index.js \
  frontend/docagent-frontend/src/pages/SearchPage.vue \
  frontend/docagent-frontend/src/components/SearchToolbar.vue \
  frontend/docagent-frontend/src/components/DocumentResultList.vue \
  frontend/docagent-frontend/src/components/DocumentReader.vue \
  frontend/docagent-frontend/src/components/TopicTreePanel.vue \
  frontend/docagent-frontend/src/components/SummaryDrawer.vue \
  frontend/docagent-frontend/src/components/ClassificationReportDrawer.vue \
  frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js \
  frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js \
  frontend/docagent-frontend/src/assets/styles/global.scss \
  frontend/docagent-frontend/src/App.vue
git commit -m "feat: rebuild search workspace around documents"
```

### Task 6: Replace The Taxonomy Page And Remove Chunk-First UI

**Files:**
- Modify: `frontend/docagent-frontend/src/pages/TaxonomyPage.vue`
- Modify: `frontend/docagent-frontend/src/router/index.js`
- Delete: `frontend/docagent-frontend/src/components/SearchResultsTable.vue`
- Delete: `frontend/docagent-frontend/src/components/DocumentPreviewPanel.vue`
- Delete: `frontend/docagent-frontend/src/components/ClassificationTablePanel.vue`
- Delete or legacy-freeze: `frontend/docagent-frontend/src/components/MultiLevelClassification.vue`

- [ ] **Step 1: Write the failing route-level smoke test or manual acceptance checklist**

Because the current frontend has no page-router test harness, create a manual acceptance checklist in the implementation notes:

```text
1. Open /search
2. Run query “README”
3. Confirm only document rows are shown
4. Click a row and confirm the reader jumps to the first hit
5. Open the topic tree and confirm the old content/file/time tree is not the default
```

- [ ] **Step 2: Replace the taxonomy page with the new topic-tree panel**

```vue
<template>
  <section class="page-stack">
    <div class="page-intro shell-panel">
      <p class="eyebrow">Topic Map</p>
      <h3>动态语义主题树</h3>
      <p>按当前文档语义自动聚类生成，不再使用固定模板分类。</p>
    </div>
    <TopicTreePanel standalone />
  </section>
</template>
```

- [ ] **Step 3: Delete the chunk-first components**

Remove the old component imports from `SearchPage.vue`, then delete the files once `npm run build` and frontend tests both pass.

- [ ] **Step 4: Run the smoke verification**

Run:
- `cd frontend/docagent-frontend && npm run test -- --run`
- `cd frontend/docagent-frontend && npm run build`
- `curl -sS -X POST http://127.0.0.1:4173/api/retrieval/workspace-search -H 'Content-Type: application/json' -d '{"query":"README","mode":"hybrid","limit":5}'`

Expected:
- tests PASS
- build PASS
- API returns a `documents[]` array with document-centric fields

- [ ] **Step 5: Commit**

```bash
git add frontend/docagent-frontend/src/pages/TaxonomyPage.vue \
  frontend/docagent-frontend/src/router/index.js
git rm frontend/docagent-frontend/src/components/SearchResultsTable.vue \
  frontend/docagent-frontend/src/components/DocumentPreviewPanel.vue \
  frontend/docagent-frontend/src/components/ClassificationTablePanel.vue
git commit -m "refactor: remove chunk-first workspace UI"
```

### Task 7: Final Compatibility Cleanup And Verification

**Files:**
- Modify: `backend/api/retrieval.py`
- Modify: `backend/api/classification.py`
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Test: `backend/test/test_retrieval_service_api.py`
- Test: `backend/test/test_document_reader_api.py`
- Test: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Write the failing cleanup regression test**

```python
def test_workspace_search_response_no_longer_requires_chunk_toggle(monkeypatch):
    payload = RetrievalService().workspace_search(query="README", mode="hybrid", limit=5)
    assert "group_by_document" not in payload.get("applied_filters", {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test/test_retrieval_service_api.py::test_workspace_search_response_no_longer_requires_chunk_toggle -v`
Expected: FAIL until the compatibility-only fields are removed.

- [ ] **Step 3: Remove obsolete compatibility fields and dead API helpers**

Delete or deprecate:
- `group_by_document` request handling
- chunk-first summary citations in the UI
- legacy multi-level tree as the default frontend source

- [ ] **Step 4: Run the full verification suite**

Run:
- `pytest -q backend/test`
- `python3 -m compileall backend`
- `cd frontend/docagent-frontend && npm run test -- --run`
- `cd frontend/docagent-frontend && npm run build`
- `curl -sS http://127.0.0.1:6008/api/retrieval/stats`
- `curl -sS -X POST http://127.0.0.1:6008/api/retrieval/workspace-search -H 'Content-Type: application/json' -d '{"query":"README","mode":"hybrid","limit":5}'`
- `curl -sS 'http://127.0.0.1:6008/api/documents/README_20260217021739.md/reader?query=DocAgentRAG'`
- `curl -sS http://127.0.0.1:6008/api/classification/topic-tree`

Expected:
- backend tests PASS
- backend compile PASS
- frontend tests PASS
- frontend build PASS
- search stats show both corpus and vector state
- workspace search returns document-centric payloads
- reader endpoint returns blocks and match ranges
- topic tree endpoint returns dynamic nodes

- [ ] **Step 5: Commit**

```bash
git add backend/api/retrieval.py \
  backend/api/classification.py \
  frontend/docagent-frontend/src/api/index.js \
  frontend/docagent-frontend/src/pages/SearchPage.vue \
  backend/test/test_retrieval_service_api.py \
  backend/test/test_document_reader_api.py \
  backend/test/test_topic_tree_service.py
git commit -m "refactor: finalize document-centric search redesign"
```
