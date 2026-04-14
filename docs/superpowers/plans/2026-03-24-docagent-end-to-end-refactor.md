# DocAgent End-to-End Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the ingestion, classification, retrieval, and web workspace flows so the system can parse documents reliably, search by filename/content/metadata, generate classification tables from results, and display documents clearly in the browser.

**Architecture:** Keep the current FastAPI + SQLite metadata + Chroma stack, but make `backend/app/services/*` the stable entry point, expand SQLite persistence for contents/segments/classification tables, and expose higher-level APIs that the Vue workspace can consume directly. Preserve current routes where possible while adding richer result payloads and document-preview endpoints.

**Tech Stack:** FastAPI, SQLite, ChromaDB, Vue 3, Element Plus, Axios, pytest

---

### Task 1: Plan and persistence shape

**Files:**
- Create: `docs/superpowers/plans/2026-03-24-docagent-end-to-end-refactor.md`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/utils/storage.py`

- [ ] Add SQLite tables for `document_contents`, `document_segments`, `classification_tables`
- [ ] Add repository helpers to read/write full content, preview segments, artifacts, and generated tables
- [ ] Keep existing document metadata APIs backward-compatible

### Task 2: Extraction contract and ingestion hardening

**Files:**
- Modify: `backend/utils/document_processor.py`
- Modify: `backend/app/services/extraction_service.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/utils/storage.py`
- Test: `backend/test/test_document_processor_contract.py`

- [ ] Write failing tests for parser failure detection and contract shape
- [ ] Return structured extraction results consistently
- [ ] Reject failed parsing during upload and rechunk
- [ ] Persist extracted full content and retrieval segments during ingestion

### Task 3: Retrieval and document preview APIs

**Files:**
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/api/retrieval.py`
- Modify: `backend/utils/retriever.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/api/document.py`
- Test: `backend/test/test_retrieval_service_api.py`

- [ ] Add filename/content/metadata-aware search request model
- [ ] Add document preview/detail endpoints backed by stored content and segments
- [ ] Add retrieval grouping metadata for document-level UI rendering
- [ ] Preserve existing endpoints while enriching payloads

### Task 4: Classification table generation flow

**Files:**
- Modify: `backend/app/services/classification_service.py`
- Modify: `backend/api/classification.py`
- Modify: `backend/utils/smart_retrieval.py`
- Modify: `backend/app/infra/metadata_store.py`
- Test: `backend/test/test_classification_tables.py`

- [ ] Add service method to generate classification tables from retrieval results
- [ ] Persist generated tables and expose list/detail APIs
- [ ] Use LLM when available, with deterministic fallback clustering/keyword grouping

### Task 5: Web workspace refactor

**Files:**
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Create: `frontend/docagent-frontend/src/components/SearchFilters.vue`
- Create: `frontend/docagent-frontend/src/components/SearchResultsTable.vue`
- Create: `frontend/docagent-frontend/src/components/DocumentPreviewPanel.vue`
- Create: `frontend/docagent-frontend/src/components/ClassificationTablePanel.vue`
- Modify: `frontend/docagent-frontend/src/components/FileUpload.vue`
- Modify: `frontend/docagent-frontend/src/assets/styles/global.scss`

- [ ] Replace the dialog-centric search flow with a three-panel workspace
- [ ] Add filters for filename, file type, category, and retrieval mode
- [ ] Show result summary, citations, preview content, and generated classification tables inline
- [ ] Allow image uploads in the same visual language as other supported file types

### Task 6: Verification and cleanup

**Files:**
- Modify: `backend/test/test_retriever.py`
- Modify: `backend/test/test_classofier.py`
- Modify: `backend/requirements.txt`

- [ ] Fix broken tests that no longer match current imports/contracts
- [ ] Add missing runtime dependencies required by the implemented features
- [ ] Run targeted pytest suites and frontend build
