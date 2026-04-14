# Router RAG Route A Phase-One Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver phase-one Word/PDF structured clause retrieval by replacing naive chunk-first retrieval with persisted structural blocks, block-aware hybrid recall, deterministic reader anchors, and a document-centric frontend contract that still falls back cleanly to legacy retrieval.

**Architecture:** Keep the current FastAPI + Vue document workspace, but add a second retrieval pipeline behind `retrieval_version=block`. Word/PDF documents are parsed into deterministic blocks, indexed into a dedicated block collection plus persisted reader artifacts, and searched through a block-aware hybrid pipeline that returns document-level evidence cards and a compatibility `results` view. Legacy chunk retrieval remains intact and is used explicitly when no block-ready documents are eligible.

**Tech Stack:** FastAPI, Pydantic, SQLite-backed metadata store, ChromaDB, existing embedding stack, Python pytest, Vue 3, Vite, Vitest, Vue Test Utils

---

## File Structure

### Backend

- Create: `backend/utils/block_extractor.py`
  - Structured Word/PDF block extraction, normalization, deterministic serialization, and `indexed_content_hash` generation.
- Create: `backend/app/services/indexing_service.py`
  - Orchestrate block extraction, block index writes, persisted reader artifacts, and document metadata updates.
- Create: `backend/scripts/backfill_block_index.py`
  - Backfill block indexes for existing documents without requiring upload/rechunk.
- Create: `backend/test/test_block_extractor.py`
  - Regression coverage for block extraction, normalization, and hash stability.
- Create: `backend/test/test_indexing_service.py`
  - Service-level tests for block index creation, replacement, and lifecycle hooks.
- Modify: `backend/app/infra/metadata_store.py`
  - Add single-artifact helpers for deterministic per-document block artifacts.
- Modify: `backend/utils/storage.py`
  - Add wrappers for deterministic block artifacts and a dedicated Chroma block collection.
- Modify: `backend/utils/retriever.py`
  - Add block BM25/vector recall helpers and keep legacy retrieval entry points untouched.
- Modify: `backend/app/services/retrieval_service.py`
  - Add retrieval-version routing, block pipeline orchestration, compatibility `results`, totals semantics, and explicit fallback metadata.
- Modify: `backend/app/services/document_service.py`
  - Read reader payloads from persisted structured blocks and trigger block indexing on upload/rechunk without breaking legacy availability.
- Modify: `backend/app/schemas/retrieval_workspace.py`
  - Extend request/response schema support for block evidence fields and retrieval-version metadata.
- Modify: `backend/app/schemas/document_reader.py`
  - Add `block_type` and `heading_path` to structured reader blocks.
- Modify: `backend/api/retrieval.py`
  - Accept `retrieval_version` on `/workspace-search`; keep request validation aligned with the new contract.
- Modify: `backend/api/document.py`
  - Keep `/documents/{id}/reader` stable while returning the new structured reader payload shape.
- Modify: `backend/test/test_metadata_store_extensions.py`
  - Lock block artifact roundtrip behavior.
- Modify: `backend/test/test_retrieval_service_api.py`
  - Lock block-mode API behavior, fallback semantics, totals, and compatibility `results`.
- Modify: `backend/test/test_document_reader_api.py`
  - Lock reader behavior against persisted structured blocks instead of raw segments.

### Frontend

- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
  - Send an explicit `retrieval_version` controlled by rollout config, keep the current document-first layout, and route only block-mode `smart` requests through sync `/workspace-search`.
- Modify: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
  - Show `heading_path`, `page_number`, and `block_type` for evidence blocks while preserving current interactions.
- Modify: `frontend/docagent-frontend/src/components/DocumentReader.vue`
  - Render structured block metadata (`heading_path`, `block_type`) and keep existing anchor navigation.
- Create: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`
  - Lock the phase-one request contract and the smart-mode sync fallback.
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`
  - Lock evidence rendering for heading path/page/block type.
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js`
  - Lock structured reader metadata rendering and anchor navigation.

### No Planned Changes

- `backend/api/retrieval.py:/workspace-search-stream`
  - Keep this endpoint on the legacy streaming contract in phase one. Do not attempt block-mode SSE in this plan.
- `frontend/docagent-frontend/src/api/index.js`
  - The existing `workspaceSearch` and `workspaceSearchStream` helpers already accept arbitrary payloads; the phase-one routing decision lives in `SearchPage.vue`.
- `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`
  - Preview work is already complete and is unrelated to retrieval-phase rollout.

---

### Task 1: Add Deterministic Block Artifact Helpers

**Files:**
- Modify: `backend/test/test_metadata_store_extensions.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/utils/storage.py`

- [ ] **Step 1: Write the failing persistence test**

Add a new test next to the current metadata-store roundtrip coverage:

```python
def test_block_artifact_helpers_upsert_single_reader_payload(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    assert store.upsert_document(
        {
            "id": "doc-1",
            "filename": "spec.docx",
            "filepath": "/tmp/spec.docx",
            "file_type": ".docx",
        },
        mirror=False,
    )

    artifact_id = store.upsert_document_artifact(
        "doc-1",
        "reader_blocks",
        {
            "index_version": "block-v1",
            "indexed_content_hash": "abc123",
            "blocks": [
                {
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                    "block_type": "paragraph",
                    "heading_path": ["第一章 总则"],
                    "text": "示例正文",
                }
            ],
        },
    )

    saved = store.get_document_artifact("doc-1", "reader_blocks")

    assert artifact_id == "doc-1:reader_blocks"
    assert saved["artifact_id"] == "doc-1:reader_blocks"
    assert saved["payload"]["blocks"][0]["block_id"] == "doc-1:block-v1:0"
```

- [ ] **Step 2: Run the targeted metadata-store test and verify it fails**

Run: `cd backend && python -m pytest test/test_metadata_store_extensions.py::test_block_artifact_helpers_upsert_single_reader_payload -v`
Expected: FAIL with `AttributeError` because `upsert_document_artifact` / `get_document_artifact` do not exist yet.

- [ ] **Step 3: Implement single-artifact helpers and storage wrappers**

Add deterministic helpers instead of list-scanning in every caller:

```python
def upsert_document_artifact(
    self,
    document_id: str,
    artifact_type: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    artifact_id = f"{document_id}:{artifact_type}"
    return self.save_document_artifact(
        document_id=document_id,
        artifact_type=artifact_type,
        payload=payload,
        artifact_id=artifact_id,
    )

def get_document_artifact(
    self,
    document_id: str,
    artifact_type: str,
) -> Optional[Dict[str, Any]]:
    artifacts = self.list_document_artifacts(document_id, artifact_type)
    return artifacts[0] if artifacts else None
```

Mirror them through `backend/utils/storage.py` so services can call:

```python
def upsert_document_artifact(document_id: str, artifact_type: str, payload: dict):
    return _metadata_store().upsert_document_artifact(document_id, artifact_type, payload)

def get_document_artifact(document_id: str, artifact_type: str):
    return _metadata_store().get_document_artifact(document_id, artifact_type)
```

- [ ] **Step 4: Re-run the targeted metadata-store test**

Run: `cd backend && python -m pytest test/test_metadata_store_extensions.py::test_block_artifact_helpers_upsert_single_reader_payload -v`
Expected: PASS.

- [ ] **Step 5: Commit the persistence helper change**

```bash
git add backend/test/test_metadata_store_extensions.py \
  backend/app/infra/metadata_store.py \
  backend/utils/storage.py
git commit -m "feat: add deterministic document artifact helpers"
```

### Task 2: Implement Structured Block Extraction And Hash Normalization

**Files:**
- Create: `backend/test/test_block_extractor.py`
- Create: `backend/utils/block_extractor.py`

- [ ] **Step 1: Write the failing extractor tests**

Create focused tests for deterministic behavior first:

```python
from utils.block_extractor import (
    assign_block_ids,
    compute_indexed_content_hash,
    normalize_block_text,
)


def test_compute_indexed_content_hash_is_stable_for_semantically_identical_blocks():
    blocks = [
        {
            "block_type": "paragraph",
            "heading_path": ["第三章 财务管理", "3.2 报销标准"],
            "page_number": 12,
            "text": "员工差旅报销标准如下。\n\n",
        }
    ]

    same_blocks = [
        {
            "block_type": "paragraph",
            "heading_path": ["  第三章 财务管理", "3.2  报销标准  "],
            "page_number": 12,
            "text": "员工差旅报销标准如下。\r\n\r\n",
        }
    ]

    assert compute_indexed_content_hash(blocks) == compute_indexed_content_hash(same_blocks)


def test_assign_block_ids_uses_document_id_index_version_and_block_index():
    blocks = [
        {"block_index": 0, "text": "A"},
        {"block_index": 1, "text": "B"},
    ]

    assign_block_ids(blocks, document_id="doc-1", index_version="block-v1")

    assert blocks[0]["block_id"] == "doc-1:block-v1:0"
    assert blocks[1]["block_id"] == "doc-1:block-v1:1"
```

Add one smoke test that runs against an existing fixture:

```python
def test_extract_structured_blocks_from_docx_preserves_heading_context():
    fixture = Path(__file__).parent / "test_date" / "sample.docx"
    payload = extract_structured_blocks(str(fixture), document_id="doc-docx")

    assert payload["blocks"]
    assert all("block_type" in block for block in payload["blocks"])
    assert all("heading_path" in block for block in payload["blocks"])
```

- [ ] **Step 2: Run the extractor test file and verify it fails**

Run: `cd backend && python -m pytest test/test_block_extractor.py -v`
Expected: FAIL because `utils.block_extractor` does not exist yet.

- [ ] **Step 3: Implement the block extractor module**

Create a focused module with explicit boundaries:

```python
BLOCK_INDEX_VERSION = "block-v1"


def extract_structured_blocks(filepath: str, document_id: str) -> dict:
    ext = Path(filepath).suffix.lower()
    if ext == ".docx":
        blocks = _extract_docx_blocks(filepath)
    elif ext == ".pdf":
        blocks = _extract_pdf_blocks(filepath)
    else:
        raise ValueError(f"block extraction not supported for {ext}")

    normalized_blocks = normalize_blocks(blocks)
    assign_block_ids(normalized_blocks, document_id=document_id, index_version=BLOCK_INDEX_VERSION)
    return {
        "index_version": BLOCK_INDEX_VERSION,
        "indexed_content_hash": compute_indexed_content_hash(normalized_blocks),
        "blocks": normalized_blocks,
    }
```

Required normalization rules:

- convert all line endings to `\n`
- trim trailing whitespace per line
- collapse repeated blank lines inside block text
- normalize `heading_path` by trimming segment edges, replacing internal newlines and tabs with spaces, collapsing repeated spaces to one space, and joining segments as ` > ` for hashing
- preserve punctuation, numbering tokens, and full-width/half-width forms exactly as extracted
- keep tables as one block unless they exceed the phase-one split threshold; when split, retain header context in each derived block

- [ ] **Step 4: Re-run the extractor tests**

Run: `cd backend && python -m pytest test/test_block_extractor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the extractor module**

```bash
git add backend/test/test_block_extractor.py \
  backend/utils/block_extractor.py
git commit -m "feat: add structured block extractor"
```

### Task 3: Build The Block Indexing Service

**Files:**
- Create: `backend/test/test_indexing_service.py`
- Create: `backend/app/services/indexing_service.py`
- Modify: `backend/utils/storage.py`

- [ ] **Step 1: Write the failing indexing-service test**

Create a focused unit test around the orchestration boundary:

```python
def test_index_document_replaces_old_block_entries_and_persists_reader_blocks(monkeypatch):
    deleted_ids = []
    added_payload = {}

    class FakeCollection:
        def get(self, where):
            assert where == {"document_id": "doc-1"}
            return {"ids": ["old-1", "old-2"]}

        def delete(self, ids):
            deleted_ids.extend(ids)

        def add(self, documents, metadatas, ids):
            added_payload["documents"] = documents
            added_payload["metadatas"] = metadatas
            added_payload["ids"] = ids

    monkeypatch.setattr(indexing_service_module, "get_document_info", lambda document_id: {
        "id": document_id,
        "filepath": "/tmp/spec.docx",
        "filename": "spec.docx",
        "file_type": ".docx",
    })
    monkeypatch.setattr(indexing_service_module, "get_block_collection", lambda: FakeCollection())
    monkeypatch.setattr(indexing_service_module, "extract_structured_blocks", lambda filepath, document_id: {
        "index_version": "block-v1",
        "indexed_content_hash": "hash-1",
        "blocks": [
            {
                "block_id": "doc-1:block-v1:0",
                "block_index": 0,
                "block_type": "paragraph",
                "file_type": ".docx",
                "file_type_family": "word",
                "heading_path": ["第一章 总则"],
                "page_number": None,
                "text": "示例正文",
                "source_parser": "python-docx",
            }
        ],
    })
    monkeypatch.setattr(indexing_service_module, "upsert_document_artifact", lambda *args, **kwargs: "doc-1:reader_blocks")

    updates = []
    monkeypatch.setattr(indexing_service_module, "update_document_info", lambda document_id, payload: updates.append((document_id, payload)) or True)

    result = IndexingService().index_document("doc-1", force=True)

    assert deleted_ids == ["old-1", "old-2"]
    assert added_payload["ids"] == ["doc-1:block-v1:0"]
    assert result["block_index_status"] == "ready"
    assert updates[-1][1]["indexed_content_hash"] == "hash-1"
    assert updates[-1][1]["block_count"] == 1
    assert "last_indexed_at" in updates[-1][1]
```

- [ ] **Step 2: Run the indexing-service test and verify it fails**

Run: `cd backend && python -m pytest test/test_indexing_service.py::test_index_document_replaces_old_block_entries_and_persists_reader_blocks -v`
Expected: FAIL because `IndexingService` and block collection helpers do not exist yet.

- [ ] **Step 3: Implement the indexing service and block collection helper**

Add a dedicated Chroma collection helper in `backend/utils/storage.py` that reuses the same embedding configuration strategy already used for the legacy `documents` collection:

```python
def get_block_collection():
    client, _ = init_chroma_client()
    return client.get_or_create_collection(
        name="document_blocks",
        embedding_function=_resolve_embedding_function(),
    )
```

Implement the orchestration service:

```python
class IndexingService:
    READER_ARTIFACT_TYPE = "reader_blocks"

    def index_document(self, document_id: str, force: bool = False) -> Dict[str, Any]:
        doc_info = get_document_info(document_id)
        payload = extract_structured_blocks(doc_info["filepath"], document_id=document_id)
        collection = get_block_collection()

        existing = collection.get(where={"document_id": document_id})
        if existing.get("ids"):
            collection.delete(ids=existing["ids"])

        collection.add(
            documents=[block["text"] for block in payload["blocks"]],
            metadatas=[self._build_block_metadata(doc_info, payload["index_version"], block) for block in payload["blocks"]],
            ids=[block["block_id"] for block in payload["blocks"]],
        )

        upsert_document_artifact(
            document_id,
            self.READER_ARTIFACT_TYPE,
            payload,
        )
        update_document_info(document_id, {
            "block_index_status": "ready",
            "index_version": payload["index_version"],
            "indexed_content_hash": payload["indexed_content_hash"],
            "block_count": len(payload["blocks"]),
            "last_indexed_at": datetime.now().isoformat(),
        })
        return {"document_id": document_id, "block_index_status": "ready"}
```

Required behavior:

- delete old block entries before adding the new version
- write one persisted reader artifact that becomes the source of truth for `/documents/{id}/reader`
- update document metadata with `block_index_status`, `index_version`, `indexed_content_hash`, `block_count`, and `last_indexed_at`
- on failure, set `block_index_status = "failed"` and capture a short error message without deleting the legacy chunk state

- [ ] **Step 4: Re-run the indexing-service test**

Run: `cd backend && python -m pytest test/test_indexing_service.py::test_index_document_replaces_old_block_entries_and_persists_reader_blocks -v`
Expected: PASS.

- [ ] **Step 5: Commit the indexing service**

```bash
git add backend/test/test_indexing_service.py \
  backend/app/services/indexing_service.py \
  backend/utils/storage.py
git commit -m "feat: add block indexing service"
```

### Task 4: Hook Block Indexing Into Document Lifecycle And Backfill

**Files:**
- Modify: `backend/test/test_indexing_service.py`
- Modify: `backend/app/services/document_service.py`
- Create: `backend/scripts/backfill_block_index.py`

- [ ] **Step 1: Add failing lifecycle-hook tests**

Extend `backend/test/test_indexing_service.py` with one document-service test:

```python
def test_rechunk_triggers_block_reindex_without_breaking_chunk_response(monkeypatch):
    monkeypatch.setattr(document_service_module, "re_chunk_document", lambda document_id, use_refiner=True: True)
    monkeypatch.setattr(document_service_module, "check_document_chunks", lambda document_id: {
        "document_id": document_id,
        "exists": True,
        "chunk_count": 4,
    })

    service = DocumentService()
    service.get_document = lambda document_id: {"id": document_id, "filename": "spec.docx"}
    service.indexing_service = Mock()
    service.indexing_service.index_document.return_value = {"document_id": "doc-1", "block_index_status": "ready"}

    payload = service.rechunk("doc-1", use_refiner=True)

    service.indexing_service.index_document.assert_called_once_with("doc-1", force=True)
    assert payload["chunk_count"] == 4
```

- [ ] **Step 2: Run the lifecycle-hook test and verify it fails**

Run: `cd backend && python -m pytest test/test_indexing_service.py::test_rechunk_triggers_block_reindex_without_breaking_chunk_response -v`
Expected: FAIL because `DocumentService` does not own an `indexing_service` yet.

- [ ] **Step 3: Wire the indexing service into upload/rechunk and add a backfill CLI**

Update `DocumentService.__init__`:

```python
class DocumentService:
    def __init__(self):
        self.extraction_service = ExtractionService()
        self.indexing_service = IndexingService()
```

After successful upload and after successful `re_chunk_document(...)`, trigger block indexing in best-effort mode:

```python
try:
    self.indexing_service.index_document(document_id, force=True)
except Exception as exc:
    logger.warning("block indexing failed for %s: %s", document_id, exc)
```

Do **not** fail upload or rechunk when block indexing fails; phase one must preserve legacy retrieval availability.

Create `backend/scripts/backfill_block_index.py` with:

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id")
    parser.add_argument("--failed-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
```

Behavior:

- default to all documents missing `block_index_status=ready`
- support `--document-id` for one-off repair
- support `--failed-only` for retrying only broken block indexes
- print per-document status and a final summary

- [ ] **Step 4: Re-run the lifecycle-hook test and the script smoke check**

Run: `cd backend && python -m pytest test/test_indexing_service.py::test_rechunk_triggers_block_reindex_without_breaking_chunk_response -v`
Expected: PASS.

Run: `cd backend && python scripts/backfill_block_index.py --help`
Expected: usage text with `--document-id`, `--failed-only`, `--limit`, and `--dry-run`.

- [ ] **Step 5: Commit the lifecycle and backfill work**

```bash
git add backend/test/test_indexing_service.py \
  backend/app/services/document_service.py \
  backend/scripts/backfill_block_index.py
git commit -m "feat: trigger and backfill block indexing"
```

### Task 5: Add Retrieval-Version Routing And Block Workspace Search

**Files:**
- Modify: `backend/test/test_retrieval_service_api.py`
- Modify: `backend/app/schemas/retrieval_workspace.py`
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/api/retrieval.py`
- Modify: `backend/utils/retriever.py`

- [ ] **Step 1: Write the failing workspace-search contract tests**

Add focused tests for both the happy path and fallback path:

```python
def test_workspace_search_block_mode_returns_documents_and_compatibility_results(monkeypatch):
    monkeypatch.setattr(retrieval_service_module, "search_block_documents", lambda **kwargs: {
        "documents": [
            {
                "document_id": "doc-1",
                "filename": "财务制度.docx",
                "file_type": ".docx",
                "score": 0.92,
                "hit_count": 3,
                "best_block_id": "doc-1:block-v1:14",
                "classification_result": "财务制度",
                "file_available": True,
                "evidence_blocks": [
                    {
                        "block_id": "doc-1:block-v1:14",
                        "block_index": 14,
                        "block_type": "paragraph",
                        "snippet": "员工差旅报销标准如下……",
                        "heading_path": ["第三章 财务管理", "3.2 报销标准"],
                        "page_number": 12,
                        "score": 0.92,
                        "match_reason": "heading + body match",
                    }
                ],
            }
        ],
        "results": [
            {
                "document_id": "doc-1",
                "block_id": "doc-1:block-v1:14",
                "block_index": 14,
                "snippet": "员工差旅报销标准如下……",
                "score": 0.92,
                "match_reason": "heading + body match",
            }
        ],
        "meta": {"fallback_used": False},
    })
    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", lambda **kwargs: {"doc-1"})

    payload = RetrievalService().workspace_search(
        query="报销标准",
        mode="hybrid",
        retrieval_version="block",
        limit=10,
        group_by_document=True,
    )

    assert payload["retrieval_version_requested"] == "block"
    assert payload["retrieval_version_used"] == "block"
    assert payload["total_documents"] == 1
    assert payload["total_results"] == 1
    assert payload["results"][0]["block_id"] == "doc-1:block-v1:14"
```

Add the fallback test:

```python
def test_workspace_search_block_mode_falls_back_to_legacy_when_no_ready_docs(monkeypatch):
    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", lambda **kwargs: set())
    monkeypatch.setattr(retrieval_service_module, "hybrid_search", lambda **kwargs: [
        {
            "document_id": "doc-legacy",
            "filename": "legacy.pdf",
            "file_type": ".pdf",
            "similarity": 0.88,
            "content_snippet": "legacy snippet",
            "chunk_index": 0,
        }
    ])
    monkeypatch.setattr(retrieval_service_module, "get_document_info", lambda document_id: {
        "id": document_id,
        "filename": "legacy.pdf",
        "file_type": ".pdf",
        "created_at_iso": "2026-04-13T00:00:00",
    })
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", lambda document_id: {"preview_content": "legacy snippet"})
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(retrieval_service_module, "get_all_documents", lambda: [])

    payload = RetrievalService().workspace_search(
        query="报销标准",
        mode="hybrid",
        retrieval_version="block",
        limit=10,
        group_by_document=True,
    )

    assert payload["retrieval_version_used"] == "legacy"
    assert payload["meta"]["fallback_used"] is True
```

- [ ] **Step 2: Run the targeted workspace-search tests and verify they fail**

Run: `cd backend && python -m pytest test/test_retrieval_service_api.py -v`
Expected: FAIL because `retrieval_version` routing, block search helpers, and compatibility `results` semantics are not implemented yet.

- [ ] **Step 3: Implement block routing, block search helpers, and cache isolation**

Extend the request schema:

```python
class WorkspaceSearchRequest(BaseModel):
    ...
    retrieval_version: Optional[str] = None
```

Update the service entry point:

```python
def workspace_search(..., retrieval_version: Optional[str] = None, ...):
    requested = self._resolve_requested_retrieval_version(retrieval_version)
    eligible_doc_ids = self._get_eligible_block_document_ids(...)

    if requested == "block" and eligible_doc_ids:
        block_payload = self._run_block_workspace_search(...)
        return {
            "query": normalized_query,
            "mode": normalized_mode,
            "retrieval_version_requested": requested,
            "retrieval_version_used": "block",
            "total_results": len(block_payload["results"]),
            "total_documents": len(block_payload["documents"]),
            "results": block_payload["results"],
            "documents": block_payload["documents"],
            "meta": block_payload["meta"],
            "applied_filters": applied_filters,
        }
```

Required rules:

- `limit` caps returned `documents` when `group_by_document=true`
- `results` under `group_by_document=true` must flatten only the surfaced `documents[].evidence_blocks[]`
- `hit_count` remains the pre-truncation matched-block count, not the number of `results`
- when no filtered block-ready documents exist, fall back to legacy and set:
  - `retrieval_version_used = "legacy"`
  - `meta.fallback_used = true`
  - `meta.fallback_reason = "no_ready_block_documents"`
- include `retrieval_version` and the rerank/query-expansion knobs in the `RetrievalService` cache-filter payload so block and legacy results cannot collide

In `backend/utils/retriever.py`, add bounded block helpers rather than rewriting legacy search:

```python
def search_block_documents(
    query: str,
    mode: str,
    limit: int,
    alpha: float,
    use_rerank: bool,
    use_llm_rerank: bool,
    file_types: List[str],
    classification: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    ready_document_ids: set[str],
) -> Dict[str, Any]:
    ...
```

Keep rerank backend order pragmatic in phase one:

1. rules-based fusion rerank always available
2. existing LLM rerank only when `use_rerank=true` and `use_llm_rerank=true`
3. no block-mode SSE work in this task

- [ ] **Step 4: Re-run the workspace-search test file**

Run: `cd backend && python -m pytest test/test_retrieval_service_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the retrieval routing work**

```bash
git add backend/test/test_retrieval_service_api.py \
  backend/app/schemas/retrieval_workspace.py \
  backend/app/services/retrieval_service.py \
  backend/api/retrieval.py \
  backend/utils/retriever.py
git commit -m "feat: add block workspace retrieval routing"
```

### Task 6: Serve Reader Payloads From Persisted Structured Blocks

**Files:**
- Modify: `backend/test/test_document_reader_api.py`
- Modify: `backend/app/schemas/document_reader.py`
- Modify: `backend/app/services/document_service.py`

- [ ] **Step 1: Write the failing reader-contract test**

Replace the segment-only assumption with a structured-block-first test:

```python
def test_get_document_reader_uses_persisted_reader_blocks_before_legacy_segments(monkeypatch):
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: {
        "id": document_id,
        "filename": "财务制度.docx",
        "file_type": ".docx",
        "classification_result": "财务制度",
        "created_at_iso": "2026-03-20T10:00:00",
    })
    monkeypatch.setattr(document_service_module, "get_document_content_record", lambda document_id: {
        "document_id": document_id,
        "parser_name": "python-docx",
        "extraction_status": "ready",
    })
    monkeypatch.setattr(document_service_module, "get_document_artifact", lambda document_id, artifact_type: {
        "artifact_id": "doc-1:reader_blocks",
        "payload": {
            "blocks": [
                {
                    "block_id": "doc-1:block-v1:14",
                    "block_index": 14,
                    "block_type": "paragraph",
                    "heading_path": ["第三章 财务管理", "3.2 报销标准"],
                    "page_number": 12,
                    "text": "员工差旅报销标准如下……",
                }
            ]
        },
    })
    monkeypatch.setattr(document_service_module, "list_document_segments", lambda document_id: [
        {"segment_id": "legacy#0", "segment_index": 0, "content": "legacy chunk"}
    ])

    payload = DocumentService().get_reader_payload("doc-1", query="报销标准", anchor_block_id="doc-1:block-v1:14")

    assert payload["best_anchor"]["block_id"] == "doc-1:block-v1:14"
    assert payload["blocks"][0]["block_type"] == "paragraph"
    assert payload["blocks"][0]["heading_path"] == ["第三章 财务管理", "3.2 报销标准"]
```

- [ ] **Step 2: Run the reader test and verify it fails**

Run: `cd backend && python -m pytest test/test_document_reader_api.py -v`
Expected: FAIL because the reader schema and service still assume `title`-based legacy segments.

- [ ] **Step 3: Update the reader schema and service**

Update `backend/app/schemas/document_reader.py`:

```python
class ReaderBlock(BaseModel):
    block_id: str
    block_index: int
    block_type: str
    heading_path: List[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    text: str
    matches: List[ReaderMatchRange] = Field(default_factory=list)
```

Refactor `DocumentService._build_reader_blocks(...)` to prefer the persisted reader artifact:

```python
artifact = get_document_artifact(document_id, "reader_blocks")
if artifact and artifact.get("payload", {}).get("blocks"):
    return [
        {
            "block_id": block["block_id"],
            "block_index": block["block_index"],
            "block_type": block["block_type"],
            "heading_path": block.get("heading_path", []),
            "page_number": block.get("page_number"),
            "text": block["text"],
        }
        for block in sorted(artifact["payload"]["blocks"], key=lambda item: item["block_index"])
    ]
```

Fallback order must be:

1. persisted `reader_blocks` artifact
2. legacy segments
3. paragraph split from full text

Do not paginate or window the reader blocks in phase one.

- [ ] **Step 4: Re-run the reader test file**

Run: `cd backend && python -m pytest test/test_document_reader_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the reader payload change**

```bash
git add backend/test/test_document_reader_api.py \
  backend/app/schemas/document_reader.py \
  backend/app/services/document_service.py
git commit -m "feat: serve reader payloads from block artifacts"
```

### Task 7: Update The Search Workspace Frontend For Block Contracts

**Files:**
- Create: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- Modify: `frontend/docagent-frontend/src/components/DocumentReader.vue`
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js`

- [ ] **Step 1: Write the failing frontend tests**

Add a SearchPage request-routing test:

```javascript
it('uses sync workspace search for block smart requests', async () => {
  const wrapper = mount(SearchPage, {
    global: {
      stubs: {
        SearchToolbar: { template: '<button class="go" @click="$emit(\'search\')">go</button>' },
        DocumentResultList: true,
        DocumentReader: true,
        SummaryDrawer: true,
        ClassificationReportDrawer: true,
        TopicTreePanel: true,
        DocumentViewerModal: true
      }
    }
  })

  wrapper.vm.filters.mode = 'smart'
  await wrapper.find('.go').trigger('click')

  expect(api.workspaceSearch).toHaveBeenCalledWith(expect.objectContaining({
    mode: 'smart',
    retrieval_version: 'block'
  }))
  expect(workspaceSearchStream).not.toHaveBeenCalled()
})

it('keeps legacy smart requests on the SSE path during rollout', async () => {
  vi.stubEnv('VITE_WORKSPACE_RETRIEVAL_VERSION', 'legacy')
  const wrapper = mount(SearchPage, { ...sameMountOptions })

  wrapper.vm.filters.mode = 'smart'
  await wrapper.find('.go').trigger('click')

  expect(workspaceSearchStream).toHaveBeenCalled()
  expect(api.workspaceSearch).not.toHaveBeenCalled()
})
```

Extend `DocumentResultList.spec.js`:

```javascript
expect(wrapper.text()).toContain('第三章 财务管理')
expect(wrapper.text()).toContain('第 12 页')
expect(wrapper.text()).toContain('paragraph')
```

Extend `DocumentReader.spec.js`:

```javascript
expect(wrapper.text()).toContain('第三章 财务管理')
expect(wrapper.text()).toContain('paragraph')
```

- [ ] **Step 2: Run the targeted frontend tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm test -- src/pages/__tests__/SearchPage.spec.js src/components/__tests__/DocumentResultList.spec.js src/components/__tests__/DocumentReader.spec.js`
Expected: FAIL because the search page does not send `retrieval_version`, `smart` still uses SSE unconditionally, and the components do not render the new block metadata.

- [ ] **Step 3: Implement the minimal frontend contract changes**

Update `SearchPage.vue` request construction:

```javascript
const WORKSPACE_RETRIEVAL_VERSION = import.meta.env.VITE_WORKSPACE_RETRIEVAL_VERSION || 'legacy'

const buildSearchRequest = () => ({
  query: filters.value.query?.trim() || '',
  mode: filters.value.mode,
  retrieval_version: WORKSPACE_RETRIEVAL_VERSION,
  limit: filters.value.limit,
  alpha: filters.value.alpha,
  use_rerank: filters.value.use_rerank,
  use_query_expansion: filters.value.use_query_expansion,
  use_llm_rerank: filters.value.use_llm_rerank,
  expansion_method: filters.value.expansion_method,
  file_types: filters.value.file_types || [],
  filename: filters.value.filename?.trim() || null,
  classification: filters.value.classification || null,
  date_from: filters.value.date_range?.[0] || null,
  date_to: filters.value.date_range?.[1] || null,
  group_by_document: true
})
```

Use sync search whenever `retrieval_version === 'block'`:

```javascript
if (req.mode === 'smart' && req.retrieval_version === 'legacy') {
  // existing SSE path
} else {
  const response = await api.workspaceSearch(req)
  await _applyWorkspaceResult(response)
}
```

Rollout rule for the frontend:

- default `VITE_WORKSPACE_RETRIEVAL_VERSION` to `legacy`
- flip it to `block` only after the backend rollout flag and block-index backfill are ready
- keep the SSE path reachable for legacy smart during rollout; only block-mode smart is intentionally synchronous in phase one

Render the new evidence metadata in `DocumentResultList.vue`:

```vue
<div class="block-meta">
  <span v-if="(block.heading_path || []).length">{{ block.heading_path.join(' > ') }}</span>
  <span v-if="block.page_number">第 {{ block.page_number }} 页</span>
  <span v-if="block.block_type">{{ block.block_type }}</span>
</div>
```

Render the same metadata in `DocumentReader.vue`:

```vue
<header>
  <span>{{ block.block_type || 'paragraph' }}</span>
  <span v-if="(block.heading_path || []).length">{{ block.heading_path.join(' > ') }}</span>
  <span v-if="block.page_number">第 {{ block.page_number }} 页</span>
</header>
```

- [ ] **Step 4: Re-run the targeted frontend tests**

Run: `cd frontend/docagent-frontend && npm test -- src/pages/__tests__/SearchPage.spec.js src/components/__tests__/DocumentResultList.spec.js src/components/__tests__/DocumentReader.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the frontend contract update**

```bash
git add frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js \
  frontend/docagent-frontend/src/pages/SearchPage.vue \
  frontend/docagent-frontend/src/components/DocumentResultList.vue \
  frontend/docagent-frontend/src/components/DocumentReader.vue \
  frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js \
  frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js
git commit -m "feat: adopt block retrieval workspace contract"
```

## Final Verification

- [ ] Run the backend regression set:
  `cd backend && python -m pytest test/test_metadata_store_extensions.py test/test_block_extractor.py test/test_indexing_service.py test/test_retrieval_service_api.py test/test_document_reader_api.py -v`
- [ ] Run the frontend regression set:
  `cd frontend/docagent-frontend && npm test -- src/pages/__tests__/SearchPage.spec.js src/components/__tests__/DocumentResultList.spec.js src/components/__tests__/DocumentReader.spec.js`
- [ ] Run a backfill dry run before changing rollout defaults:
  `cd backend && python scripts/backfill_block_index.py --dry-run --limit 20`
- [ ] Perform one manual smoke search after backfill:
  1. start backend: `cd backend && python main.py`
  2. start frontend: `cd frontend/docagent-frontend && npm run dev`
  3. search for a clause query such as `报销标准`
  4. verify the response exposes `retrieval_version_used = block`, evidence cards show heading/page context, and the reader scrolls to `best_anchor.block_id`

## Rollout Notes

1. Keep the server-side default retrieval version on `legacy` until the backfill script has indexed a meaningful subset of existing Word/PDF documents.
2. Run `python scripts/backfill_block_index.py --dry-run` first, then re-run without `--dry-run` in batches if the corpus is large.
3. After backfill, inspect a few document metadata records and confirm `block_index_status=ready`, `index_version=block-v1`, and `indexed_content_hash` are present.
4. Only then flip the rollout default for omitted `retrieval_version` to `block`.
5. Do not change `workspace-search-stream` in this phase; block-mode `smart` stays synchronous by design here.
