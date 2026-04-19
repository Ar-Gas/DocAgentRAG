# LightRAG Async Document Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make document upload non-blocking, track LightRAG ingest status explicitly, and expose a document audit so local files, legacy metadata, and LightRAG state stop drifting silently.

**Architecture:** Keep DocAgentRAG as the local shell that owns uploaded files and SQLite metadata. Add a small LightRAG HTTP client, persist queued/processing/ready/failed ingest states, run upload-to-LightRAG work in a bounded background executor, and expose admin audit endpoints for local metadata/files and LightRAG health. Existing Chroma/block reader code remains in place as compatibility code for now.

**Tech Stack:** FastAPI, SQLite, httpx, asyncio background tasks, Vue 3, Element Plus, pytest, Vitest

---

## File Structure

### Backend

- Create: `backend/app/infra/lightrag_client.py`
- Create: `backend/app/services/document_audit_service.py`
- Create: `backend/test/test_lightrag_client.py`
- Create: `backend/test/test_document_service_async_ingest.py`
- Create: `backend/test/test_document_audit_service.py`
- Modify: `backend/config.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/api/document.py`
- Modify: `backend/api/admin.py`
- Modify: `backend/main.py`

### Frontend

- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/components/FileUpload.vue`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`

## Task 1: LightRAG Client And Config

**Files:**
- Create: `backend/app/infra/lightrag_client.py`
- Create: `backend/test/test_lightrag_client.py`
- Modify: `backend/config.py`
- Modify: `backend/requirements.txt`

- [ ] Write failing tests for config defaults, `X-API-Key` headers, upload-file response normalization, and non-2xx error mapping.
- [ ] Add `LIGHTRAG_BASE_URL`, `LIGHTRAG_API_KEY`, `LIGHTRAG_TIMEOUT_SECONDS`, `LIGHTRAG_ENABLED`, and LightRAG error codes.
- [ ] Add `httpx` to backend requirements.
- [ ] Implement `LightRAGClient.health()`, `upload_file()`, and `get_track_status()`.
- [ ] Verify with `cd backend && python3 -m pytest test/test_lightrag_client.py -v`.

## Task 2: Document Metadata Status Fields

**Files:**
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] Write failing tests that a queued upload returns a persisted document with `ingest_status=queued` and later status updates persist in both table columns and payload.
- [ ] Add SQLite columns with idempotent `ALTER TABLE`: `ingest_status`, `ingest_error`, `lightrag_track_id`, `lightrag_doc_id`, `last_status_sync_at`.
- [ ] Include the new fields in document serialization and `upsert_document`.
- [ ] Add repository helpers for status updates and LightRAG IDs.
- [ ] Verify with `cd backend && python3 -m pytest test/test_document_service_async_ingest.py -v`.

## Task 3: Async Upload Pipeline

**Files:**
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/api/document.py`
- Test: `backend/test/test_document_service_async_ingest.py`

- [ ] Write failing tests that `DocumentService.upload()` saves the file and returns before calling a blocking parser/indexer.
- [ ] Write failing tests that `process_pending_ingest(document_id)` marks processing, calls LightRAG, stores `track_id`, and records failed errors without deleting the local file.
- [ ] Replace synchronous extraction/indexing in the upload request path with metadata creation and background enqueue.
- [ ] Keep a direct method for retrying ingest by document ID.
- [ ] Add response fields: `ingest_status`, `ingest_error`, `lightrag_track_id`, `lightrag_doc_id`.
- [ ] Verify with `cd backend && python3 -m pytest test/test_document_service_async_ingest.py test/test_document_empty_state.py test/test_document_reader_api.py -v`.

## Task 4: Startup And Admin Audit

**Files:**
- Create: `backend/app/services/document_audit_service.py`
- Create: `backend/test/test_document_audit_service.py`
- Modify: `backend/api/admin.py`
- Modify: `backend/main.py`

- [ ] Write failing tests that audit reports SQLite document count, local file count, untracked local files, legacy JSON count, LightRAG health, and pending ingest documents.
- [ ] Implement audit service without mutating data by default.
- [ ] Add `GET /api/v1/admin/document-audit`.
- [ ] Add startup audit log summary and LightRAG health check when enabled; do not auto-import or delete files.
- [ ] Verify with `cd backend && python3 -m pytest test/test_document_audit_service.py -v`.

## Task 5: Frontend Status Display

**Files:**
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/components/FileUpload.vue`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`

- [ ] Update upload copy from “上传并分类成功” to “已保存，正在导入知识库”.
- [ ] Show `ingest_status` tags in the document table.
- [ ] Show `ingest_error` in a compact warning area for failed rows.
- [ ] Add a retry ingest action that calls `POST /documents/{id}/retry-ingest`.
- [ ] Refresh the document list shortly after upload and on retry completion.
- [ ] Verify with `cd frontend/docagent-frontend && npm run test -- FileList`.

## Task 6: Final Verification

- [ ] Run backend targeted tests:
  `cd backend && python3 -m pytest test/test_lightrag_client.py test/test_document_service_async_ingest.py test/test_document_audit_service.py test/test_document_empty_state.py test/test_document_reader_api.py -v`
- [ ] Run frontend targeted tests:
  `cd frontend/docagent-frontend && npm run test -- FileList`
- [ ] Run `git diff --stat` and summarize changed behavior.

