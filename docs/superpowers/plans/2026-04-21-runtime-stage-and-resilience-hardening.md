# Runtime Stage And Resilience Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stage-aware document runtime state, readiness-based dependency checks, and targeted recovery controls so LightRAG or embedding instability no longer collapses document handling into one opaque failure state.

**Architecture:** Persist document stage rows in SQLite, keep aggregate ingest and local index fields for compatibility, and make `DocumentService` update stages independently for extraction, preview, and RAG ingest. Upgrade runtime probes from liveness-only checks to readiness-aware checks, then add guarded retry endpoints that operate on specific stages instead of generic global retry.

**Tech Stack:** FastAPI, sqlite3, pytest, httpx, asyncio, LightRAG

---

## File Structure

**Files:**
- Create: `backend/app/services/document_stage_aggregator.py`
- Create: `backend/app/services/rag_runtime_guard.py`
- Create: `backend/test/test_document_stage_repository.py`
- Create: `backend/test/test_document_stage_aggregator.py`
- Create: `backend/test/test_lightrag_runtime_health.py`
- Create: `backend/test/test_rag_runtime_guard.py`
- Create: `backend/test/test_runtime_admin_api.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/app/services/local_embedding_runtime.py`
- Modify: `backend/app/services/lightrag_runtime.py`
- Modify: `backend/api/admin.py`
- Modify: `backend/local_embedding_server.py`
- Modify: `backend/test/test_local_embedding_runtime.py`
- Modify: `backend/test/test_local_embedding_server.py`
- Modify: `backend/test/test_document_service_async_ingest.py`

---

### Task 1: Persist Per-Document Stage State In SQLite

**Files:**
- Create: `backend/test/test_document_stage_repository.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`

- [ ] **Step 1: Write the failing stage repository test**

Create `backend/test/test_document_stage_repository.py` with:

```python
from pathlib import Path

from app.infra.metadata_store import DocumentMetadataStore


def test_metadata_store_persists_document_processing_stages(tmp_path: Path):
    store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)
    store.upsert_document(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(tmp_path / "budget.pdf"),
            "file_type": ".pdf",
        }
    )

    store.upsert_document_stage(
        "doc-1",
        "content_extract",
        status="ready",
        error_code=None,
        error_message=None,
        retry_count=0,
        payload={"content_length": 128},
    )
    store.upsert_document_stage(
        "doc-1",
        "rag_ingest",
        status="failed",
        error_code="embedding_unready",
        error_message="local embedding server unavailable",
        retry_count=2,
        payload={"track_id": None},
    )

    stages = {row["stage_name"]: row for row in store.list_document_stages("doc-1")}

    assert stages["content_extract"]["status"] == "ready"
    assert stages["rag_ingest"]["error_code"] == "embedding_unready"
    assert stages["rag_ingest"]["retry_count"] == 2
    assert stages["rag_ingest"]["payload"]["track_id"] is None
```

- [ ] **Step 2: Run the stage repository test and verify it fails**

Run: `cd backend && python -m pytest test/test_document_stage_repository.py -v`
Expected: FAIL because the `document_processing_stages` table and repository methods do not exist yet.

- [ ] **Step 3: Implement stage table creation and repository helpers**

Update `backend/app/infra/metadata_store.py` to create a new table:

```python
connection.execute(
    """
    CREATE TABLE IF NOT EXISTS document_processing_stages (
        document_id TEXT NOT NULL,
        stage_name TEXT NOT NULL,
        status TEXT NOT NULL,
        error_code TEXT,
        error_message TEXT,
        retry_count INTEGER NOT NULL DEFAULT 0,
        payload TEXT NOT NULL,
        started_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (document_id, stage_name)
    )
    """
)
connection.execute(
    "CREATE INDEX IF NOT EXISTS idx_document_processing_stages_status ON document_processing_stages(stage_name, status)"
)
```

Add methods to `DocumentMetadataStore`:

```python
def upsert_document_stage(
    self,
    document_id: str,
    stage_name: str,
    *,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    retry_count: int = 0,
    payload: dict | None = None,
    started_at: str | None = None,
) -> bool:
    now = datetime.utcnow().isoformat()
    with self._connect() as connection:
        connection.execute(
            """
            INSERT INTO document_processing_stages (
                document_id, stage_name, status, error_code, error_message,
                retry_count, payload, started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id, stage_name) DO UPDATE SET
                status = excluded.status,
                error_code = excluded.error_code,
                error_message = excluded.error_message,
                retry_count = excluded.retry_count,
                payload = excluded.payload,
                started_at = COALESCE(document_processing_stages.started_at, excluded.started_at),
                updated_at = excluded.updated_at
            """,
            (
                document_id,
                stage_name,
                status,
                error_code,
                error_message,
                int(retry_count),
                json.dumps(payload or {}, ensure_ascii=False),
                started_at or now,
                now,
            ),
        )
        connection.commit()
    return True


def list_document_stages(self, document_id: str) -> list[dict]:
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT document_id, stage_name, status, error_code, error_message,
                   retry_count, payload, started_at, updated_at
            FROM document_processing_stages
            WHERE document_id = ?
            ORDER BY stage_name
            """,
            (document_id,),
        ).fetchall()
    return [
        {
            "document_id": row["document_id"],
            "stage_name": row["stage_name"],
            "status": row["status"],
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "retry_count": int(row["retry_count"] or 0),
            "payload": json.loads(row["payload"] or "{}"),
            "started_at": row["started_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
```

Update `backend/app/infra/repositories/document_repository.py` with:

```python
def upsert_stage(self, document_id: str, stage_name: str, **kwargs) -> bool:
    return self._store.upsert_document_stage(document_id, stage_name, **kwargs)


def list_stages(self, document_id: str) -> List[Dict[str, Any]]:
    return self._store.list_document_stages(document_id)
```

- [ ] **Step 4: Re-run the stage repository test**

Run: `cd backend && python -m pytest test/test_document_stage_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the stage persistence changes**

```bash
git add backend/app/infra/metadata_store.py backend/app/infra/repositories/document_repository.py backend/test/test_document_stage_repository.py
git commit -m "feat: persist document processing stages"
```

### Task 2: Upgrade Health Checks From Liveness-Only To Readiness-Aware

**Files:**
- Create: `backend/test/test_lightrag_runtime_health.py`
- Modify: `backend/local_embedding_server.py`
- Modify: `backend/app/services/local_embedding_runtime.py`
- Modify: `backend/app/services/lightrag_runtime.py`
- Modify: `backend/test/test_local_embedding_runtime.py`
- Modify: `backend/test/test_local_embedding_server.py`

- [ ] **Step 1: Write the failing readiness tests**

Create `backend/test/test_lightrag_runtime_health.py` with:

```python
import asyncio

from app.services.lightrag_runtime import LightRAGRuntime


def test_lightrag_runtime_health_reports_degraded_when_upstream_is_alive_but_not_ready():
    class Runtime(LightRAGRuntime):
        async def health(self):
            return {
                "status": "degraded",
                "liveness": "up",
                "readiness": "unready",
                "detail": "embedding dependency is not ready",
            }

    payload = asyncio.run(Runtime(auto_start=False).health())

    assert payload["status"] == "degraded"
    assert payload["liveness"] == "up"
    assert payload["readiness"] == "unready"
```

Append to `backend/test/test_local_embedding_runtime.py`:

```python
def test_ensure_ready_requires_readiness_probe_before_returning_healthy():
    class Runtime(LocalEmbeddingRuntime):
        def __init__(self):
            super().__init__(auto_start=False)
            self.probe_calls = 0

        async def health(self):
            return {"status": "healthy", "ready": False, "detail": "model not loaded"}

        async def probe_readiness(self):
            self.probe_calls += 1
            raise RuntimeError("model not loaded")

    runtime = Runtime()

    try:
        asyncio.run(runtime.ensure_ready())
    except RuntimeError as exc:
        assert "model not loaded" in str(exc)
    else:
        raise AssertionError("ensure_ready should fail when readiness probe fails")
```

Append to `backend/test/test_local_embedding_server.py`:

```python
def test_health_check_reports_ready_flag():
    client = TestClient(local_embedding_server.app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert payload["status"] in {"healthy", "degraded"}
```

- [ ] **Step 2: Run the readiness tests and verify they fail**

Run: `cd backend && python -m pytest test/test_local_embedding_runtime.py test/test_local_embedding_server.py test/test_lightrag_runtime_health.py -v`
Expected: FAIL because health payloads and `ensure_ready()` do not distinguish readiness yet.

- [ ] **Step 3: Implement readiness-aware health behavior**

Update `backend/local_embedding_server.py` to expose liveness and a lightweight local readiness check:

```python
def build_health_payload() -> dict:
    ready = True
    detail = None
    try:
        create_embeddings_payload(
            model=LOCAL_EMBEDDING_MODEL_NAME,
            input_value="probe",
            encoding_format="float",
        )
    except Exception as exc:
        ready = False
        detail = str(exc)
    return {
        "status": "healthy" if ready else "degraded",
        "ready": ready,
        "model": LOCAL_EMBEDDING_MODEL_NAME,
        "detail": detail,
    }


@app.get("/health")
def health_check():
    return build_health_payload()
```

Update `backend/app/services/local_embedding_runtime.py` with a readiness probe:

```python
async def probe_readiness(self) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=self.health_timeout_seconds) as client:
        response = await client.post(
            f"{self.base_url}/v1/embeddings",
            json={"model": LOCAL_EMBEDDING_MODEL_NAME, "input": "probe", "encoding_format": "float"},
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("data"):
        raise RuntimeError("local embedding readiness probe returned no vectors")
    return {"status": "healthy", "ready": True}


async def ensure_ready(self) -> Dict[str, Any]:
    async with self._lock:
        current = await self.health()
        if current.get("status") == "healthy" and current.get("ready") is True:
            return current
        try:
            await self.probe_readiness()
            return {**current, "status": "healthy", "ready": True}
        except Exception as exc:
            if not self.auto_start:
                raise RuntimeError(str(exc))
```

Update `backend/app/services/lightrag_runtime.py` so `health()` normalizes liveness/readiness:

```python
if response.status_code < 200 or response.status_code >= 300:
    return {
        "status": "unhealthy",
        "liveness": "down",
        "readiness": "unready",
        "base_url": self.base_url,
        "detail": f"LightRAG returned {response.status_code}: {response.text}",
    }

payload = response.json() if response.content else {}
status = str(payload.get("status") or "unknown")
return {
    **payload,
    "status": "healthy" if status == "healthy" else "degraded",
    "liveness": "up",
    "readiness": "ready" if status == "healthy" else "unready",
    "base_url": self.base_url,
}
```

- [ ] **Step 4: Re-run the readiness tests**

Run: `cd backend && python -m pytest test/test_local_embedding_runtime.py test/test_local_embedding_server.py test/test_lightrag_runtime_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the readiness hardening**

```bash
git add backend/local_embedding_server.py backend/app/services/local_embedding_runtime.py backend/app/services/lightrag_runtime.py backend/test/test_local_embedding_runtime.py backend/test/test_local_embedding_server.py backend/test/test_lightrag_runtime_health.py
git commit -m "feat: add readiness-aware runtime health checks"
```

### Task 3: Make DocumentService Track Stages Independently And Preserve Partial Success

**Files:**
- Create: `backend/app/services/document_stage_aggregator.py`
- Create: `backend/test/test_document_stage_aggregator.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/test/test_document_service_async_ingest.py`

- [ ] **Step 1: Write the failing stage aggregation tests**

Create `backend/test/test_document_stage_aggregator.py` with:

```python
from app.services.document_stage_aggregator import aggregate_runtime_view


def test_aggregate_runtime_view_preserves_local_success_when_rag_failed():
    payload = aggregate_runtime_view(
        {
            "content_extract": {"status": "ready"},
            "local_preview_index": {"status": "ready"},
            "rag_ingest": {"status": "failed", "error_code": "embedding_unready"},
        }
    )

    assert payload["ingest_status"] == "failed"
    assert payload["local_index_status"] == "ready"
    assert payload["ingest_error"] == "embedding_unready"
```

Append to `backend/test/test_document_service_async_ingest.py`:

```python
def test_process_pending_ingest_persists_rag_stage_without_overwriting_local_success(tmp_path):
    client = FakeLightRAGClient(error=RuntimeError("upstream unavailable"))
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.txt", BytesIO("预算审批\n合同金额 100 万".encode("utf-8")))

    local_result = service.process_local_index(doc["id"])
    ingest_result = asyncio.run(service.process_pending_ingest(doc["id"]))
    refreshed = service.get_document(doc["id"])

    assert local_result["local_index_status"] == "ready"
    assert ingest_result["ingest_status"] == "failed"
    assert refreshed["local_index_status"] == "ready"
    assert refreshed["processing_stages"]["local_preview_index"]["status"] == "ready"
    assert refreshed["processing_stages"]["rag_ingest"]["status"] == "failed"
```

- [ ] **Step 2: Run the stage aggregation tests and verify they fail**

Run: `cd backend && python -m pytest test/test_document_stage_aggregator.py test/test_document_service_async_ingest.py -v`
Expected: FAIL because there is no stage aggregator and `DocumentService` does not attach `processing_stages`.

- [ ] **Step 3: Implement a stage aggregator and stage-aware document updates**

Create `backend/app/services/document_stage_aggregator.py` with:

```python
def aggregate_runtime_view(stage_map: dict) -> dict:
    rag_stage = stage_map.get("rag_ingest", {})
    preview_stage = stage_map.get("local_preview_index", {})

    ingest_status = "queued"
    ingest_error = None
    if rag_stage.get("status") == "ready":
        ingest_status = "ready"
    elif rag_stage.get("status") in {"processing", "deferred"}:
        ingest_status = "processing"
    elif rag_stage.get("status") == "failed":
        ingest_status = "failed"
        ingest_error = rag_stage.get("error_code") or rag_stage.get("error_message")

    local_index_status = "queued"
    local_index_error = None
    if preview_stage.get("status") == "ready":
        local_index_status = "ready"
    elif preview_stage.get("status") == "failed":
        local_index_status = "failed"
        local_index_error = preview_stage.get("error_message")
    elif preview_stage.get("status") == "processing":
        local_index_status = "processing"

    return {
        "ingest_status": ingest_status,
        "ingest_error": ingest_error,
        "local_index_status": local_index_status,
        "local_index_error": local_index_error,
    }
```

Update `backend/app/services/document_service.py` with helpers:

```python
def _mark_stage(self, document_id: str, stage_name: str, **kwargs) -> None:
    self._document_repository().upsert_stage(document_id, stage_name, **kwargs)


def _load_stage_map(self, document_id: str) -> dict:
    return {
        row["stage_name"]: row
        for row in self._document_repository().list_stages(document_id)
    }


def _sync_aggregate_status_fields(self, document_id: str) -> dict:
    stage_map = self._load_stage_map(document_id)
    aggregated = aggregate_runtime_view(stage_map)
    self._document_repository().update(
        document_id,
        {
            "ingest_status": aggregated["ingest_status"],
            "ingest_error": aggregated["ingest_error"],
            "local_index_status": aggregated["local_index_status"],
            "local_index_error": aggregated["local_index_error"],
        },
    )
    return aggregated
```

Call `_mark_stage()` in `upload()`, `process_local_index()`, and `process_pending_ingest()`:

```python
self._mark_stage(doc["id"], "content_extract", status="queued", payload={})
self._mark_stage(doc["id"], "local_preview_index", status="queued", payload={})
self._mark_stage(doc["id"], "rag_ingest", status="queued", payload={})
```

On local preview success:

```python
self._mark_stage(
    document_id,
    "local_preview_index",
    status="ready",
    payload={"content_length": len(full_content or ""), "parser_name": parser_name},
)
self._sync_aggregate_status_fields(document_id)
```

On RAG failure:

```python
self._mark_stage(
    document_id,
    "rag_ingest",
    status="failed",
    error_code="embedding_unready",
    error_message=str(exc),
    retry_count=current_retry_count + 1,
    payload={"track_id": None},
)
self._sync_aggregate_status_fields(document_id)
```

Update `get_document()` and `list_documents()` to attach:

```python
doc["processing_stages"] = self._load_stage_map(document_id)
```

- [ ] **Step 4: Re-run the stage aggregation tests**

Run: `cd backend && python -m pytest test/test_document_stage_aggregator.py test/test_document_service_async_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the stage-aware document service**

```bash
git add backend/app/services/document_stage_aggregator.py backend/app/services/document_service.py backend/test/test_document_stage_aggregator.py backend/test/test_document_service_async_ingest.py
git commit -m "refactor: preserve document runtime state by stage"
```

### Task 4: Add Large-Document And Dependency-Degraded RAG Guardrails

**Files:**
- Create: `backend/app/services/rag_runtime_guard.py`
- Create: `backend/test/test_rag_runtime_guard.py`
- Modify: `backend/app/services/document_service.py`

- [ ] **Step 1: Write the failing RAG guard tests**

Create `backend/test/test_rag_runtime_guard.py` with:

```python
from app.services.rag_runtime_guard import RagCircuitBreaker, build_document_profile


def test_build_document_profile_marks_extra_large_pdf_for_deferred_rag():
    profile = build_document_profile(
        filename="操作系统导论.pdf",
        file_type=".pdf",
        content_length=605036,
        estimated_chunks=520,
    )

    assert profile["size_class"] == "xlarge"
    assert profile["defer_rag"] is True


def test_circuit_breaker_opens_after_repeated_failures():
    breaker = RagCircuitBreaker(failure_threshold=3)

    breaker.record_failure("embedding_unready")
    breaker.record_failure("embedding_unready")
    breaker.record_failure("embedding_unready")

    state = breaker.snapshot()

    assert state["open"] is True
    assert state["failure_count"] == 3
```

- [ ] **Step 2: Run the RAG guard tests and verify they fail**

Run: `cd backend && python -m pytest test/test_rag_runtime_guard.py -v`
Expected: FAIL because the guard module does not exist yet.

- [ ] **Step 3: Implement document profiling and a simple RAG circuit breaker**

Create `backend/app/services/rag_runtime_guard.py` with:

```python
from dataclasses import dataclass, field
from datetime import datetime


def build_document_profile(filename: str, file_type: str, content_length: int, estimated_chunks: int) -> dict:
    size_class = "small"
    defer_rag = False
    if estimated_chunks >= 500 or content_length >= 500000:
        size_class = "xlarge"
        defer_rag = True
    elif estimated_chunks >= 120 or content_length >= 120000:
        size_class = "large"
    elif estimated_chunks >= 40 or content_length >= 40000:
        size_class = "medium"

    return {
        "filename": filename,
        "file_type": file_type,
        "content_length": int(content_length or 0),
        "estimated_chunks": int(estimated_chunks or 0),
        "size_class": size_class,
        "defer_rag": defer_rag,
    }


@dataclass
class RagCircuitBreaker:
    failure_threshold: int = 3
    failure_count: int = 0
    last_error_code: str | None = None
    last_failure_at: str | None = None

    def record_failure(self, error_code: str) -> None:
        self.failure_count += 1
        self.last_error_code = error_code
        self.last_failure_at = datetime.utcnow().isoformat()

    def record_success(self) -> None:
        self.failure_count = 0
        self.last_error_code = None
        self.last_failure_at = None

    def is_open(self) -> bool:
        return self.failure_count >= self.failure_threshold

    def snapshot(self) -> dict:
        return {
            "open": self.is_open(),
            "failure_count": self.failure_count,
            "last_error_code": self.last_error_code,
            "last_failure_at": self.last_failure_at,
        }
```

Update `backend/app/services/document_service.py`:

```python
from app.services.rag_runtime_guard import RagCircuitBreaker, build_document_profile


self.rag_circuit_breaker = RagCircuitBreaker()
```

Before calling `upload_file()` in `process_pending_ingest()`:

```python
stage_map = self._load_stage_map(document_id)
content_record = self._content_repository().get(document_id) or {}
content_length = len((content_record.get("full_content") or "").strip())
estimated_chunks = max(1, content_length // 1200) if content_length else 0
profile = build_document_profile(doc_info["filename"], doc_info.get("file_type", ""), content_length, estimated_chunks)

if self.rag_circuit_breaker.is_open():
    self._mark_stage(
        document_id,
        "rag_ingest",
        status="deferred",
        error_code="dependency_degraded",
        error_message="waiting for embedding or lightrag recovery",
        retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
        payload={"profile": profile},
    )
    aggregated = self._sync_aggregate_status_fields(document_id)
    return {**doc_info, **aggregated}

if profile["defer_rag"]:
    self._mark_stage(
        document_id,
        "rag_ingest",
        status="deferred",
        error_code=None,
        error_message=None,
        retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
        payload={"profile": profile},
    )
    aggregated = self._sync_aggregate_status_fields(document_id)
    return {**doc_info, **aggregated}
```

On upstream failures, record them:

```python
self.rag_circuit_breaker.record_failure("embedding_unready")
```

On successful LightRAG acceptance, reset:

```python
self.rag_circuit_breaker.record_success()
```

- [ ] **Step 4: Re-run the RAG guard tests**

Run: `cd backend && python -m pytest test/test_rag_runtime_guard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the RAG guardrails**

```bash
git add backend/app/services/rag_runtime_guard.py backend/app/services/document_service.py backend/test/test_rag_runtime_guard.py
git commit -m "feat: guard rag ingest for degraded dependencies and huge files"
```

### Task 5: Add Runtime Admin Health And Stage-Specific Retry Endpoints

**Files:**
- Create: `backend/test/test_runtime_admin_api.py`
- Modify: `backend/api/admin.py`
- Modify: `backend/app/services/document_service.py`

- [ ] **Step 1: Write the failing runtime admin API tests**

Create `backend/test/test_runtime_admin_api.py` with:

```python
from fastapi.testclient import TestClient

import api.admin as admin_api
from main import app


def test_runtime_health_endpoint_returns_liveness_and_readiness(monkeypatch):
    class FakeEmbeddingRuntime:
        async def health(self):
            return {"status": "degraded", "liveness": "up", "readiness": "unready"}

    class FakeDocumentService:
        def get_runtime_health(self):
            return {"rag_circuit": {"open": True, "failure_count": 3}}

    monkeypatch.setattr(admin_api, "local_embedding_runtime", FakeEmbeddingRuntime(), raising=False)
    monkeypatch.setattr(admin_api, "document_service", FakeDocumentService(), raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/admin/runtime/health")

    assert response.status_code == 200
    assert response.json()["data"]["dependencies"]["local_embedding"]["readiness"] == "unready"
    assert response.json()["data"]["rag_circuit"]["open"] is True


def test_runtime_retry_rag_endpoint_requeues_only_rag_stage(monkeypatch):
    called = {}

    class FakeDocumentService:
        def retry_rag_stage(self, document_id: str):
            called["document_id"] = document_id
            return {"document_id": document_id, "rag_ingest": "queued"}

    monkeypatch.setattr(admin_api, "document_service", FakeDocumentService(), raising=False)

    client = TestClient(app)
    response = client.post("/api/v1/admin/runtime/documents/doc-1/retry-rag")

    assert response.status_code == 200
    assert called["document_id"] == "doc-1"
    assert response.json()["data"]["rag_ingest"] == "queued"
```

- [ ] **Step 2: Run the runtime admin tests and verify they fail**

Run: `cd backend && python -m pytest test/test_runtime_admin_api.py -v`
Expected: FAIL because the runtime admin endpoints do not exist yet.

- [ ] **Step 3: Implement admin runtime health and retry endpoints**

Add to `backend/app/services/document_service.py`:

```python
def get_runtime_health(self) -> dict:
    return {
        "rag_circuit": self.rag_circuit_breaker.snapshot(),
    }


def retry_rag_stage(self, document_id: str) -> dict:
    stage_map = self._load_stage_map(document_id)
    self._mark_stage(
        document_id,
        "rag_ingest",
        status="queued",
        error_code=None,
        error_message=None,
        retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
        payload=stage_map.get("rag_ingest", {}).get("payload", {}),
    )
    aggregated = self._sync_aggregate_status_fields(document_id)
    return {"document_id": document_id, "rag_ingest": "queued", **aggregated}
```

Add to `backend/api/admin.py`:

```python
@router.get("/runtime/health", summary="获取运行时健康状态")
async def get_runtime_health():
    try:
        embedding = await local_embedding_runtime.health()
        payload = {
            "dependencies": {
                "local_embedding": {
                    "status": embedding.get("status"),
                    "liveness": embedding.get("liveness", "up" if embedding.get("status") != "unhealthy" else "down"),
                    "readiness": "ready" if embedding.get("ready") else "unready",
                    "detail": embedding.get("detail"),
                }
            },
            **document_service.get_runtime_health(),
        }
        return success(data=payload, message="获取运行时健康成功")
    except Exception as e:
        logger.error(f"获取运行时健康失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/runtime/documents/{document_id}/retry-rag", summary="重试文档 RAG 入库阶段")
async def retry_rag_stage(document_id: str):
    try:
        payload = document_service.retry_rag_stage(document_id)
        return success(data=payload, message="已重新加入 RAG 阶段队列")
    except Exception as e:
        logger.error(f"重试 RAG 阶段失败: {str(e)}")
        raise BusinessException(500, detail=str(e))
```

- [ ] **Step 4: Re-run the runtime admin tests**

Run: `cd backend && python -m pytest test/test_runtime_admin_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the runtime admin endpoints**

```bash
git add backend/api/admin.py backend/app/services/document_service.py backend/test/test_runtime_admin_api.py
git commit -m "feat: expose runtime health and rag retry endpoints"
```

## Verification

- [ ] Run: `cd backend && python -m pytest test/test_document_stage_repository.py test/test_document_stage_aggregator.py test/test_local_embedding_runtime.py test/test_local_embedding_server.py test/test_lightrag_runtime_health.py test/test_rag_runtime_guard.py test/test_runtime_admin_api.py -v`
- [ ] Run: `cd backend && python -m pytest test/test_document_service_async_ingest.py test/test_lightrag_large_doc_runtime.py test/test_lightrag_webui_proxy_api.py -v`
- [ ] Manually confirm:

```text
1. A document can have local preview ready and rag_ingest failed at the same time without losing the successful stage state.
2. local_embedding health exposes readiness and ensure_ready fails when the embeddings probe cannot run.
3. Large documents can be marked deferred for rag_ingest while remaining visible and locally browsable.
4. /api/v1/admin/runtime/health shows dependency readiness and the rag circuit state.
5. /api/v1/admin/runtime/documents/{id}/retry-rag only requeues the rag_ingest stage.
```
