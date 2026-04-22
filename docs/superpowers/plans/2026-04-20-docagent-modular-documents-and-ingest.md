# DocAgent Modular Documents And Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad hoc document metadata and in-memory ingest orchestration with explicit `documents` and `ingest` modules, persisted lifecycle state, persisted jobs, and LightRAG-backed sync behavior.

**Architecture:** Build documents and ingest as the first true business modules. SQLite becomes the control-plane owner of document and ingest state. The ingest workflow persists versions, blocks, jobs, and LightRAG sync markers. The worker drives long-running transitions. Existing upload and document endpoints delegate into the new services through compatibility shims.

**Tech Stack:** FastAPI, sqlite3, Alembic, LightRAG gateway, pytest, asyncio

---

## File Structure

**Files:**
- Create: `backend/app/modules/documents/api.py`
- Create: `backend/app/modules/documents/schemas.py`
- Create: `backend/app/modules/documents/service.py`
- Create: `backend/app/modules/documents/domain.py`
- Create: `backend/app/modules/documents/repository.py`
- Create: `backend/app/modules/documents/contracts.py`
- Create: `backend/app/modules/documents/README.md`
- Create: `backend/app/modules/ingest/api.py`
- Create: `backend/app/modules/ingest/schemas.py`
- Create: `backend/app/modules/ingest/service.py`
- Create: `backend/app/modules/ingest/state_machine.py`
- Create: `backend/app/modules/ingest/repository.py`
- Create: `backend/app/modules/ingest/contracts.py`
- Create: `backend/app/modules/ingest/README.md`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/api/document.py`
- Modify: `backend/worker.py`
- Create: `backend/test/modules/documents/test_document_service_contract.py`
- Create: `backend/test/modules/ingest/test_ingest_state_machine.py`
- Create: `backend/test/modules/ingest/test_ingest_service_contract.py`

---

### Task 1: Persist Document Versions And Ingest Jobs

**Files:**
- Modify: `backend/app/infra/metadata_store.py`
- Create: `backend/test/modules/ingest/test_ingest_repository_contract.py`

- [ ] **Step 1: Write the failing persistence contract test**

Create `backend/test/modules/ingest/test_ingest_repository_contract.py` with:

```python
from pathlib import Path

from app.infra.metadata_store import DocumentMetadataStore


def test_metadata_store_persists_versions_and_ingest_jobs(tmp_path: Path):
    store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)

    document_id = store.insert_document(
        {
            "filename": "report.pdf",
            "file_type": ".pdf",
            "file_path": str(tmp_path / "report.pdf"),
            "lifecycle_status": "registered",
        }
    )
    version_id = store.insert_document_version(
        {
            "document_id": document_id,
            "content_hash": "hash-1",
            "parser_profile": "pdf/default",
            "status": "stored",
        }
    )
    job_id = store.insert_ingest_job(
        {
            "document_id": document_id,
            "version_id": version_id,
            "job_type": "ingest_document",
            "status": "queued",
            "stage": "stored",
        }
    )

    jobs = store.list_ingest_jobs(document_id)

    assert version_id
    assert job_id
    assert jobs[0]["status"] == "queued"
```

- [ ] **Step 2: Run the repository contract test and verify it fails**

Run: `cd backend && python -m pytest test/modules/ingest/test_ingest_repository_contract.py::test_metadata_store_persists_versions_and_ingest_jobs -v`
Expected: FAIL because the new insert and list methods do not exist yet.

- [ ] **Step 3: Implement explicit document/version/job persistence**

Update `backend/app/infra/metadata_store.py` to add:

```python
def insert_document(self, payload: dict) -> str: ...
def insert_document_version(self, payload: dict) -> str: ...
def insert_ingest_job(self, payload: dict) -> str: ...
def list_ingest_jobs(self, document_id: str) -> list[dict]: ...
def update_document_lifecycle(self, document_id: str, status: str) -> bool: ...
def update_lightrag_sync(self, document_id: str, version_id: str, payload: dict) -> bool: ...
```

Add schema creation for:

```sql
CREATE TABLE IF NOT EXISTS document_versions (...);
CREATE TABLE IF NOT EXISTS ingest_jobs (...);
CREATE TABLE IF NOT EXISTS lightrag_documents (...);
```

- [ ] **Step 4: Re-run the repository contract test**

Run: `cd backend && python -m pytest test/modules/ingest/test_ingest_repository_contract.py::test_metadata_store_persists_versions_and_ingest_jobs -v`
Expected: PASS.

- [ ] **Step 5: Commit the persistence changes**

```bash
git add backend/app/infra/metadata_store.py backend/test/modules/ingest/test_ingest_repository_contract.py
git commit -m "feat: persist document versions and ingest jobs"
```

### Task 2: Build The Documents Module

**Files:**
- Create: `backend/app/modules/documents/api.py`
- Create: `backend/app/modules/documents/schemas.py`
- Create: `backend/app/modules/documents/service.py`
- Create: `backend/app/modules/documents/domain.py`
- Create: `backend/app/modules/documents/repository.py`
- Create: `backend/app/modules/documents/contracts.py`
- Create: `backend/app/modules/documents/README.md`
- Create: `backend/test/modules/documents/test_document_service_contract.py`

- [ ] **Step 1: Write the failing document service contract**

Create `backend/test/modules/documents/test_document_service_contract.py` with:

```python
from pathlib import Path

from app.modules.documents.service import DocumentService


def test_document_service_registers_document_and_returns_view(tmp_path: Path):
    service = DocumentService(data_dir=tmp_path, doc_dir=tmp_path / "doc")
    (tmp_path / "doc").mkdir()

    view = service.register_uploaded_file(
        filename="report.pdf",
        file_bytes=b"pdf",
        file_type=".pdf",
    )

    assert view.document_id
    assert view.lifecycle_status == "registered"
    assert view.filename == "report.pdf"
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `cd backend && python -m pytest test/modules/documents/test_document_service_contract.py::test_document_service_registers_document_and_returns_view -v`
Expected: FAIL because the module does not exist yet.

- [ ] **Step 3: Implement the documents module**

Create `backend/app/modules/documents/schemas.py` with:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentView:
    document_id: str
    filename: str
    file_type: str
    lifecycle_status: str
    active_version_id: str | None
```

Create `backend/app/modules/documents/service.py` with:

```python
from pathlib import Path
from uuid import uuid4

from app.modules.documents.schemas import DocumentView
from app.modules.documents.repository import DocumentsRepository


class DocumentService:
    def __init__(self, data_dir: Path, doc_dir: Path):
        self.repository = DocumentsRepository(data_dir=data_dir)
        self.doc_dir = Path(doc_dir)

    def register_uploaded_file(self, filename: str, file_bytes: bytes, file_type: str) -> DocumentView:
        document_id = str(uuid4())
        self.doc_dir.mkdir(parents=True, exist_ok=True)
        target = self.doc_dir / f"{document_id}{file_type}"
        target.write_bytes(file_bytes)
        self.repository.insert_document(
            {
                "document_id": document_id,
                "filename": filename,
                "file_type": file_type,
                "file_path": str(target),
                "lifecycle_status": "registered",
            }
        )
        return DocumentView(document_id=document_id, filename=filename, file_type=file_type, lifecycle_status="registered", active_version_id=None)
```

Write `README.md` documenting responsibility, public entry points, allowed dependencies, forbidden dependencies, and test command.

- [ ] **Step 4: Re-run the contract test**

Run: `cd backend && python -m pytest test/modules/documents/test_document_service_contract.py::test_document_service_registers_document_and_returns_view -v`
Expected: PASS.

- [ ] **Step 5: Commit the documents module**

```bash
git add backend/app/modules/documents backend/test/modules/documents/test_document_service_contract.py
git commit -m "feat: add modular documents service"
```

### Task 3: Build The Ingest Module And State Machine

**Files:**
- Create: `backend/app/modules/ingest/api.py`
- Create: `backend/app/modules/ingest/schemas.py`
- Create: `backend/app/modules/ingest/service.py`
- Create: `backend/app/modules/ingest/state_machine.py`
- Create: `backend/app/modules/ingest/repository.py`
- Create: `backend/app/modules/ingest/contracts.py`
- Create: `backend/app/modules/ingest/README.md`
- Create: `backend/test/modules/ingest/test_ingest_state_machine.py`
- Create: `backend/test/modules/ingest/test_ingest_service_contract.py`
- Modify: `backend/worker.py`

- [ ] **Step 1: Write the failing ingest tests**

Create `backend/test/modules/ingest/test_ingest_state_machine.py` with:

```python
from app.modules.ingest.state_machine import next_document_status


def test_next_document_status_moves_from_extracting_to_extracted():
    assert next_document_status("extracting", "extract_ok") == "extracted"
```

Create `backend/test/modules/ingest/test_ingest_service_contract.py` with:

```python
import pytest

from app.modules.ingest.service import IngestService


class DummyGateway:
    async def ingest_document(self, command):
        return type("Result", (), {"track_id": "track-1", "remote_document_id": "remote-1"})


@pytest.mark.asyncio
async def test_ingest_service_marks_lightrag_sync_pending(tmp_path):
    service = IngestService(data_dir=tmp_path, lightrag_gateway=DummyGateway())

    result = await service.enqueue(document_id="doc-1", version_id="ver-1")

    assert result.status == "queued"
```

- [ ] **Step 2: Run the ingest tests and verify they fail**

Run: `cd backend && python -m pytest test/modules/ingest/test_ingest_state_machine.py test/modules/ingest/test_ingest_service_contract.py -v`
Expected: FAIL because the ingest module does not exist yet.

- [ ] **Step 3: Implement the ingest state machine and enqueue flow**

Create `backend/app/modules/ingest/state_machine.py` with:

```python
TRANSITIONS = {
    ("registered", "file_stored"): "stored",
    ("stored", "extract_start"): "extracting",
    ("extracting", "extract_ok"): "extracted",
    ("extracted", "index_local_start"): "indexing_local",
    ("indexing_local", "index_local_ok"): "syncing_lightrag",
    ("syncing_lightrag", "sync_ok"): "ready",
}


def next_document_status(current: str, event: str) -> str:
    return TRANSITIONS[(current, event)]
```

Create `backend/app/modules/ingest/schemas.py` with:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestJobView:
    job_id: str
    document_id: str
    version_id: str
    status: str
    stage: str
```

Create `backend/app/modules/ingest/service.py` with an `enqueue` method that inserts an ingest job in SQLite and returns `IngestJobView`.

Update `backend/worker.py` to load the next queued job from the ingest repository and print a placeholder execution trace for now.

- [ ] **Step 4: Re-run the ingest tests**

Run: `cd backend && python -m pytest test/modules/ingest/test_ingest_state_machine.py test/modules/ingest/test_ingest_service_contract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the ingest module**

```bash
git add backend/app/modules/ingest backend/worker.py backend/test/modules/ingest
git commit -m "feat: add modular ingest state machine and queue"
```

### Task 4: Wire v1 Document Endpoints Through Compatibility Shims

**Files:**
- Modify: `backend/api/document.py`

- [ ] **Step 1: Add a compatibility test for existing document upload**

Use the existing document API tests and add one focused assertion in `backend/test/test_document_api_contract.py`:

```python
def test_upload_returns_document_lifecycle_status(client):
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("report.pdf", b"pdf", "application/pdf")},
    )

    assert response.status_code == 200
    assert "lifecycle_status" in response.json()["data"]
```

- [ ] **Step 2: Run the targeted API test and verify it fails**

Run: `cd backend && python -m pytest test/test_document_api_contract.py::test_upload_returns_document_lifecycle_status -v`
Expected: FAIL until the endpoint starts returning the new field.

- [ ] **Step 3: Update `backend/api/document.py` to delegate**

Replace direct module-global service use with a compatibility wrapper:

```python
from app.modules.documents.service import DocumentService as ModularDocumentService


def _documents_service() -> ModularDocumentService:
    return ModularDocumentService(data_dir=DATA_DIR, doc_dir=DOC_DIR)
```

Map the returned `DocumentView` into the existing response shape while adding `lifecycle_status`.

- [ ] **Step 4: Re-run the targeted API test**

Run: `cd backend && python -m pytest test/test_document_api_contract.py::test_upload_returns_document_lifecycle_status -v`
Expected: PASS.

- [ ] **Step 5: Commit the v1 compatibility wiring**

```bash
git add backend/api/document.py backend/test/test_document_api_contract.py
git commit -m "refactor: route v1 document api through modular services"
```

## Verification

- [ ] Run: `cd backend && python -m pytest test/modules/documents test/modules/ingest test/test_document_api_contract.py -v`
- [ ] Run: `cd backend && python worker.py`
- [ ] Manually confirm:

```text
1. Upload creates a registered document and a queued ingest job.
2. Document rows, version rows, and ingest job rows exist in SQLite.
3. Existing document list/detail/delete routes still respond.
4. Module READMEs exist for documents and ingest.
```
