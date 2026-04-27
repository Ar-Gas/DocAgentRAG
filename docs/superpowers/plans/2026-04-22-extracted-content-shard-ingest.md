# Extracted Content Shard Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split oversized documents after extraction by actual content length, create logical shard documents named with `-1`, `-2`, and ingest those shards sequentially while keeping the original upload as the parent record.

**Architecture:** Keep the existing upload and extraction entrypoints, extend document metadata to model parent/shard relationships, generate shard child documents after extraction succeeds, and make parent ingest delegate to shard ingest in order. Parent runtime state becomes a view aggregated from child shard states, while non-sharded documents keep the current path.

**Tech Stack:** FastAPI backend, Python services under `backend/app/services`, SQLite metadata store, pytest/unittest-style backend tests.

---

## File Map

- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/test/test_document_service_async_ingest.py`
- Add: `docs/superpowers/specs/2026-04-22-extracted-content-shard-ingest-design.md`
- Add: `docs/superpowers/plans/2026-04-22-extracted-content-shard-ingest.md`

### Task 1: Lock Shard Behavior With Failing Tests

**Files:**
- Modify: `backend/test/test_document_service_async_ingest.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Write the failing test for shard creation after extraction**

```python
def test_process_local_index_creates_shards_from_extracted_large_content(tmp_path):
    ...
    assert refreshed["shard_count"] == 2
    assert shard_names == ["manual-1.pdf", "manual-2.pdf"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k shard_creation -q`
Expected: FAIL because shard metadata and shard documents do not exist yet.

- [ ] **Step 3: Write the failing test for parent ingest delegating to shards in order**

```python
def test_process_pending_ingest_uses_ordered_shards_instead_of_parent_upload(tmp_path):
    ...
    assert client.uploads == [
        {"file_path": parent["filepath"], "filename": "manual-1.pdf"},
        {"file_path": parent["filepath"], "filename": "manual-2.pdf"},
    ]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k ordered_shards -q`
Expected: FAIL because the parent document is still uploaded directly.

- [ ] **Step 5: Write the failing test for parent status aggregation**

```python
def test_get_document_aggregates_parent_status_from_shards(tmp_path):
    ...
    assert parent["ingest_status"] == "failed"
    assert "second shard failed" in parent["ingest_error"]
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k parent_status -q`
Expected: FAIL because parent documents do not aggregate child shard state yet.

### Task 2: Extend Metadata For Parent/Shard Documents

**Files:**
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Add parent/shard fields to SQLite serialization and upsert**

```python
{
    "parent_document_id": payload.get("parent_document_id"),
    "is_shard": bool(payload.get("is_shard")),
    "shard_index": payload.get("shard_index"),
    "shard_count": payload.get("shard_count"),
    "shard_content_length": payload.get("shard_content_length"),
    "shard_group_id": payload.get("shard_group_id"),
}
```

- [ ] **Step 2: Add idempotent `ALTER TABLE` support for the new document columns**

Run: no separate command; verified by the tests in Task 1 after reinitializing the temp DB.

- [ ] **Step 3: Add repository helpers for listing child shards by parent**

```python
def list_by_parent(self, parent_document_id: str) -> List[Dict[str, Any]]:
    return self._store.list_documents_by_parent(parent_document_id)
```

- [ ] **Step 4: Run targeted tests**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k shard -q`
Expected: still FAIL, but now because service behavior is missing instead of persistence fields missing.

### Task 3: Implement Shard Planning And Creation In Document Service

**Files:**
- Modify: `backend/app/services/document_service.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Add extracted-content shard thresholds and split helpers**

```python
LIGHTRAG_SHARD_CONTENT_THRESHOLD = 120000
LIGHTRAG_SHARD_TARGET_SIZE = 90000
LIGHTRAG_SHARD_HARD_LIMIT = 100000
```

- [ ] **Step 2: Implement paragraph-first splitting with hard-limit fallback**

```python
def _split_extracted_content(self, content: str) -> List[str]:
    ...
```

- [ ] **Step 3: Create or refresh shard child documents after successful extraction**

```python
def _sync_shard_documents(...):
    ...
```

- [ ] **Step 4: Ensure parent documents with shards are marked as aggregate-only for ingest**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k shard_creation -q`
Expected: PASS

### Task 4: Route Ingest Through Ordered Shards

**Files:**
- Modify: `backend/app/services/document_service.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Add helpers to detect parent shard groups and load children in `shard_index` order**

```python
def _list_document_shards(self, document_id: str) -> List[Dict]:
    ...
```

- [ ] **Step 2: Make `process_pending_ingest(parent_id)` delegate sequentially to each shard**

```python
for shard in shards:
    result = await self.process_pending_ingest(shard["id"])
```

- [ ] **Step 3: Preserve current ingest path for non-sharded documents**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k "ordered_shards or stores_lightrag_track_id" -q`
Expected: PASS

### Task 5: Aggregate Parent Runtime State And Retry Semantics

**Files:**
- Modify: `backend/app/services/document_service.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Aggregate parent `ingest_status` / `ingest_error` from child shards during read paths**

```python
def _aggregate_shard_runtime(self, parent_doc: Dict, shards: List[Dict]) -> Dict:
    ...
```

- [ ] **Step 2: Expose shard summaries from `get_document_payload()`**

```python
return {**doc_info, "shards": shard_payloads, ...}
```

- [ ] **Step 3: Reset child shard ingest state when retrying a parent**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -k "parent_status or retry" -q`
Expected: PASS

### Task 6: Regression Verification

**Files:**
- Modify: none
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Run the focused backend regression suite**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_document_service_async_ingest.py -q`
Expected: PASS

- [ ] **Step 2: Run the broader ingest/runtime suite impacted by recent fixes**

Run: `cd backend && ../.venv/bin/python -m pytest test/test_local_embedding_server.py test/test_dev_supervisor.py test/test_lightrag_dev_config.py test/test_doubao_config.py test/test_document_service_async_ingest.py test/test_main_block_index.py -q`
Expected: PASS
