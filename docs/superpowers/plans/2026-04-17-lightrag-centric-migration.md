# LightRAG-Centric Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DocAgentRAG’s local retrieval, QA, and graph core with a LightRAG-first backend and matching frontend flows while preserving local file storage and SQLite metadata.

**Architecture:** Keep DocAgentRAG as the local shell that owns files, metadata, and stable `/api/v1/*` routes. Move retrieval, QA, graph, and indexing orchestration behind a single `LightRAGClient`, normalize LightRAG responses in application services, and simplify the frontend to render LightRAG-native results instead of local block-reader artifacts.

**Tech Stack:** FastAPI, SQLite, httpx, SSE, Vue 3, Vite, Element Plus, pytest, asyncio

---

## File Structure

### Backend

- Create: `backend/app/infra/lightrag_client.py`
- Create: `backend/test/test_lightrag_client.py`
- Create: `backend/test/test_document_service_lightrag.py`
- Create: `backend/test/test_retrieval_service_lightrag.py`
- Create: `backend/test/test_qa_service_lightrag.py`
- Create: `backend/test/test_topics_lightrag.py`
- Modify: `backend/config.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/main.py`
- Modify: `backend/api/document.py`
- Modify: `backend/api/retrieval.py`
- Modify: `backend/api/qa.py`
- Modify: `backend/api/topics.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/app/services/qa_service.py`
- Modify: `backend/app/schemas/qa.py`
- Modify: `backend/test/test_document_empty_state.py`
- Modify: `backend/test/test_main_block_index.py`

### Frontend

- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/components/FileUpload.vue`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/components/QASessionPanel.vue`
- Create: `frontend/docagent-frontend/src/components/LightRagResultList.vue`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/QAPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/GraphPage.vue`

### Cleanup

- Delete: `backend/utils/block_extractor.py`
- Delete: `backend/utils/retriever.py`
- Delete: `backend/utils/smart_retrieval.py`
- Delete: `backend/app/infra/vector_store.py`
- Delete: `backend/app/infra/embedding_provider.py`
- Delete: `backend/app/domain/llm/qa_chain.py`
- Delete: `backend/app/domain/llm/gateway.py`
- Delete: `backend/app/services/topic_tree_service.py`
- Delete: `backend/app/services/indexing_service.py`
- Delete: `backend/app/services/document_vector_index_service.py`
- Delete: `backend/app/services/ingest_pipeline.py`
- Delete: `backend/test/test_retriever.py`
- Delete: `backend/test/test_storage.py`
- Delete: `backend/test/test_indexing_service.py`
- Delete: `backend/test/test_document_reader_api.py`
- Delete: `backend/test/test_backfill_block_index.py`
- Delete: `backend/test/test_block_extractor.py`
- Delete: `backend/test/test_topic_tree_service.py`
- Delete: `backend/test/test_topic_labeler_and_embedding_provider.py`
- Delete: `frontend/docagent-frontend/src/pages/TaxonomyPage.vue`
- Delete: `frontend/docagent-frontend/src/composables/useSearch.js`
- Delete: `frontend/docagent-frontend/src/composables/useDocumentReader.js`
- Delete: `frontend/docagent-frontend/src/composables/useSummary.js`
- Delete: `frontend/docagent-frontend/src/components/ClassificationPanel.vue`
- Delete: `frontend/docagent-frontend/src/components/DocumentReader.vue`
- Delete: `frontend/docagent-frontend/src/components/TopicTreePanel.vue`
- Delete: `frontend/docagent-frontend/src/components/SummaryDrawer.vue`
- Delete: `frontend/docagent-frontend/src/components/ClassificationReportDrawer.vue`
- Delete: `frontend/docagent-frontend/src/components/SearchToolbar.vue`
- Delete: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- Delete: `frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js`
- Delete: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`
- Delete: `frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js`
- Delete: `frontend/docagent-frontend/src/components/__tests__/SearchToolbar.spec.js`

### No Planned Changes In This Plan

- `backend/app/services/classification_service.py`
  - Keep current optional classification behavior. Do not expand its scope during this migration.
- `backend/api/classification.py`
  - Classification APIs remain available but are no longer part of the primary retrieval/search experience.

---

### Task 1: Add LightRAG Configuration And Client

**Files:**
- Create: `backend/app/infra/lightrag_client.py`
- Create: `backend/test/test_lightrag_client.py`
- Modify: `backend/config.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Write the failing LightRAG client tests**

Create `backend/test/test_lightrag_client.py` with:

```python
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as config_module
from app.services.errors import AppServiceError


def test_config_reads_lightrag_values_from_env(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
    monkeypatch.setenv("LIGHTRAG_API_KEY", "secret-key")
    monkeypatch.setenv("LIGHTRAG_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("LIGHTRAG_QUERY_MODE_DEFAULT", "mix")

    import importlib
    import config

    importlib.reload(config)

    assert config.LIGHTRAG_BASE_URL == "http://127.0.0.1:9621"
    assert config.LIGHTRAG_API_KEY == "secret-key"
    assert config.LIGHTRAG_TIMEOUT_SECONDS == 12.0
    assert config.LIGHTRAG_QUERY_MODE_DEFAULT == "mix"


def test_query_data_uses_x_api_key_header(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"status": "success", "data": {"chunks": []}, "metadata": {}}

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None):
            calls["request"] = {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "files": files,
            }
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", FakeAsyncClient)
    client = client_module.LightRAGClient(
        base_url="http://127.0.0.1:9621",
        api_key="secret-key",
        timeout_seconds=12,
    )

    payload = asyncio.run(client.query_data("预算审批", mode="hybrid", top_k=5))

    assert payload["status"] == "success"
    assert calls["request"]["headers"]["X-API-Key"] == "secret-key"
    assert calls["request"]["json"]["query"] == "预算审批"
    assert calls["request"]["json"]["mode"] == "hybrid"


def test_non_2xx_response_becomes_app_service_error(monkeypatch):
    class FakeResponse:
        status_code = 503
        text = "upstream failed"

        def json(self):
            return {"detail": "upstream failed"}

        def raise_for_status(self):
            raise RuntimeError("boom")

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None):
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    client = client_module.LightRAGClient(
        base_url="http://127.0.0.1:9621",
        api_key="secret-key",
        timeout_seconds=12,
    )

    try:
        asyncio.run(client.health())
    except AppServiceError as exc:
        assert exc.code == 4001
        assert "LightRAG" in exc.detail
    else:
        raise AssertionError("expected AppServiceError")
```

- [ ] **Step 2: Run the client tests and verify they fail**

Run: `cd backend && python3 -m pytest test/test_lightrag_client.py -v`

Expected: FAIL because LightRAG config values and `app.infra.lightrag_client` do not exist yet.

- [ ] **Step 3: Implement LightRAG config and the HTTP client**

Modify `backend/config.py` to add:

```python
LIGHTRAG_BASE_URL = _get_secret_or_env("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
LIGHTRAG_API_KEY = _get_secret_or_env("LIGHTRAG_API_KEY", "")
LIGHTRAG_TIMEOUT_SECONDS = float(_get_secret_or_env("LIGHTRAG_TIMEOUT_SECONDS", "30"))
LIGHTRAG_QUERY_MODE_DEFAULT = _get_secret_or_env("LIGHTRAG_QUERY_MODE_DEFAULT", "hybrid")

ERROR_CODES.update({
    4001: "LightRAG 服务不可用",
    4002: "LightRAG 请求失败",
    4003: "LightRAG 上传失败",
})
```

Create `backend/app/infra/lightrag_client.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from app.services.errors import AppServiceError
from config import (
    LIGHTRAG_API_KEY,
    LIGHTRAG_BASE_URL,
    LIGHTRAG_TIMEOUT_SECONDS,
)


class LightRAGClient:
    def __init__(
        self,
        base_url: str = LIGHTRAG_BASE_URL,
        api_key: str = LIGHTRAG_API_KEY,
        timeout_seconds: float = LIGHTRAG_TIMEOUT_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    headers=self._headers(),
                    **kwargs,
                )
        except Exception as exc:
            raise AppServiceError(4001, f"LightRAG request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = getattr(response, "text", "") or f"HTTP {response.status_code}"
            raise AppServiceError(4001, f"LightRAG returned {response.status_code}: {detail}")

        return response

    async def health(self) -> dict[str, Any]:
        response = await self._request("GET", "/health")
        return response.json()

    async def query_data(self, text: str, mode: str, top_k: int) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/query/data",
            json={"query": text, "mode": mode, "top_k": top_k},
        )
        return response.json()

    async def query(self, text: str, mode: str, include_references: bool = True, include_chunk_content: bool = True) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/query",
            json={
                "query": text,
                "mode": mode,
                "include_references": include_references,
                "include_chunk_content": include_chunk_content,
            },
        )
        return response.json()

    async def upload_file(self, file_path: str, filename: str) -> dict[str, Any]:
        with open(file_path, "rb") as handle:
            response = await self._request(
                "POST",
                "/documents/upload",
                files={"file": (filename, handle)},
            )
        return response.json()

    async def get_track_status(self, track_id: str) -> dict[str, Any]:
        response = await self._request("GET", f"/documents/track_status/{track_id}")
        return response.json()

    async def query_stream(self, text: str, mode: str):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                "/query/stream",
                headers=self._headers(),
                json={
                    "query": text,
                    "mode": mode,
                    "stream": True,
                    "include_references": True,
                    "include_chunk_content": True,
                },
            ) as response:
                if response.status_code >= 400:
                    raise AppServiceError(4002, f"LightRAG stream failed: {response.text}")
                async for line in response.aiter_lines():
                    yield line

    async def delete_documents(self, doc_ids: list[str], delete_file: bool = False, delete_llm_cache: bool = False) -> dict[str, Any]:
        response = await self._request(
            "DELETE",
            "/documents/delete_document",
            json={
                "doc_ids": doc_ids,
                "delete_file": delete_file,
                "delete_llm_cache": delete_llm_cache,
            },
        )
        return response.json()
```

Modify `backend/requirements.txt` to add:

```text
httpx>=0.27,<0.29
```

- [ ] **Step 4: Re-run the client tests**

Run: `cd backend && python3 -m pytest test/test_lightrag_client.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the client foundation**

```bash
git add backend/config.py \
  backend/requirements.txt \
  backend/app/infra/lightrag_client.py \
  backend/test/test_lightrag_client.py
git commit -m "feat: add lightrag config and client"
```

### Task 2: Rewrite Metadata Persistence And Document Upload/Delete Flow

**Files:**
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/repositories/document_repository.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/api/document.py`
- Create: `backend/test/test_document_service_lightrag.py`
- Modify: `backend/test/test_document_empty_state.py`

- [ ] **Step 1: Write the failing document service tests**

Create `backend/test/test_document_service_lightrag.py` with:

```python
import asyncio
import io
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.document_service import DocumentService


class FakeLightRAGClient:
    def __init__(self):
        self.deleted = []

    async def upload_file(self, file_path: str, filename: str):
        return {"status": "success", "track_id": "upload-1", "message": "queued"}

    async def get_track_status(self, track_id: str):
        return {
            "documents": [
                {
                    "id": "doc-remote-1",
                    "status": "PROCESSED",
                    "track_id": track_id,
                    "file_path": "budget.pdf",
                }
            ],
            "status_summary": {"PROCESSED": 1},
        }

    async def delete_documents(self, doc_ids, delete_file=False, delete_llm_cache=False):
        self.deleted.append((doc_ids, delete_file, delete_llm_cache))
        return {"status": "deletion_started", "doc_id": ",".join(doc_ids)}


class FakeDuplicateLightRAGClient(FakeLightRAGClient):
    async def upload_file(self, file_path: str, filename: str):
        return {"status": "duplicated", "track_id": "upload-old", "message": "already exists"}


async def _read_bytes(path: Path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def test_upload_persists_track_id_and_syncs_remote_doc_id(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    data_dir.mkdir()
    doc_dir.mkdir()

    service = DocumentService(
        lightrag_client=FakeLightRAGClient(),
        data_dir=data_dir,
        doc_dir=doc_dir,
    )

    created = asyncio.run(service.upload("budget.pdf", io.BytesIO(b"budget body")))
    listing = asyncio.run(service.list_documents(page=1, page_size=20))

    assert created["lightrag_track_id"] == "upload-1"
    assert listing["items"][0]["lightrag_doc_id"] == "doc-remote-1"
    assert listing["items"][0]["index_status"] == "ready"


def test_duplicate_upload_cleans_local_file_and_metadata(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    data_dir.mkdir()
    doc_dir.mkdir()

    service = DocumentService(
        lightrag_client=FakeDuplicateLightRAGClient(),
        data_dir=data_dir,
        doc_dir=doc_dir,
    )

    result = asyncio.run(service.upload("budget.pdf", io.BytesIO(b"budget body")))
    listing = asyncio.run(service.list_documents(page=1, page_size=20))

    assert result["index_status"] == "duplicated"
    assert listing["items"] == []
    assert [path for path in doc_dir.rglob("*") if path.is_file()] == []


def test_delete_document_calls_remote_delete_before_local_cleanup(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    data_dir.mkdir()
    doc_dir.mkdir()
    client = FakeLightRAGClient()

    service = DocumentService(
        lightrag_client=client,
        data_dir=data_dir,
        doc_dir=doc_dir,
    )

    created = asyncio.run(service.upload("budget.pdf", io.BytesIO(b"budget body")))
    document_id = created["id"]

    payload = asyncio.run(service.delete_document(document_id))

    assert payload["deleted"] is True
    assert client.deleted == [(["doc-remote-1"], False, False)]
```

Replace `backend/test/test_document_empty_state.py` with:

```python
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.document_service import DocumentService


def test_list_documents_returns_empty_page_when_repository_raises(monkeypatch):
    service = DocumentService()
    monkeypatch.setattr(service, "_list_all_documents", lambda: (_ for _ in ()).throw(RuntimeError("sqlite unavailable")))

    payload = asyncio.run(service.list_documents(1, 20))

    assert payload == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 0,
    }
```

- [ ] **Step 2: Run the document service tests and verify they fail**

Run: `cd backend && python3 -m pytest test/test_document_service_lightrag.py test/test_document_empty_state.py -v`

Expected: FAIL because `DocumentService` is still synchronous, still depends on extraction/indexing services, and does not understand LightRAG status fields.

- [ ] **Step 3: Implement LightRAG-first document persistence**

Modify `backend/app/infra/metadata_store.py` so payload JSON stays in sync with status changes:

```python
def update_document_status(
    self,
    document_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> bool:
    current = self.get_document(document_id)
    if current is None:
        return False

    current["index_status"] = status
    current["status"] = status
    current["index_error"] = error_message
    current["error_message"] = error_message
    current["updated_at"] = datetime.now().isoformat()
    return self.upsert_document(current)
```

Modify `backend/app/services/document_service.py` around a LightRAG-first async service:

```python
from __future__ import annotations

import io
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from app.infra.lightrag_client import LightRAGClient
from app.infra.repositories.document_repository import DocumentRepository
from app.services.errors import AppServiceError


class DocumentService:
    def __init__(self, lightrag_client=None, document_repository=None, data_dir=DATA_DIR, doc_dir=DOC_DIR):
        self.lightrag_client = lightrag_client or LightRAGClient()
        self.document_repository = document_repository or DocumentRepository(data_dir=data_dir)
        self.data_dir = Path(data_dir)
        self.doc_dir = Path(doc_dir)

    def _list_all_documents(self):
        return self.document_repository.list_all()

    async def upload(self, filename: str, file_stream) -> dict:
        safe_name = Path(filename).name
        ext = Path(safe_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AppServiceError(2001, "不支持的文件类型")

        target_dir = self.doc_dir / EXTENSION_TO_DIR.get(ext, "other")
        target_dir.mkdir(parents=True, exist_ok=True)
        document_id = uuid.uuid4().hex
        stored_path = target_dir / f"{document_id}{ext}"

        with open(stored_path, "wb") as handle:
            shutil.copyfileobj(file_stream, handle)

        now = datetime.now().isoformat()
        doc_info = {
            "id": document_id,
            "filename": safe_name,
            "filepath": str(stored_path),
            "file_type": ext.lstrip("."),
            "created_at_iso": now,
            "updated_at": now,
            "index_status": "queued",
            "status": "queued",
            "classification_result": None,
            "lightrag_track_id": None,
            "lightrag_doc_id": None,
            "index_error": None,
            "file_available": True,
        }
        self.document_repository.upsert(doc_info)

        result = await self.lightrag_client.upload_file(str(stored_path), safe_name)
        if result.get("status") == "duplicated":
            self.document_repository.delete(document_id)
            if stored_path.exists():
                stored_path.unlink()
            return {**doc_info, "index_status": "duplicated", "lightrag_track_id": result.get("track_id")}

        if result.get("status") != "success":
            self.document_repository.update(document_id, {
                "index_status": "failed",
                "status": "failed",
                "index_error": result.get("message") or "upload failed",
            })
            raise AppServiceError(4003, result.get("message") or "LightRAG upload failed")

        self.document_repository.update(document_id, {
            "lightrag_track_id": result.get("track_id"),
            "index_status": "processing",
            "status": "processing",
        })
        return self.document_repository.get(document_id)

    async def _sync_pending_document(self, doc_info: dict) -> dict:
        track_id = doc_info.get("lightrag_track_id")
        if not track_id or doc_info.get("index_status") not in {"queued", "processing"}:
            return doc_info

        remote = await self.lightrag_client.get_track_status(track_id)
        documents = list(remote.get("documents") or [])
        if not documents:
            return doc_info

        first = documents[0]
        remote_status = (first.get("status") or "").upper()
        if remote_status == "PROCESSED":
            update = {
                "lightrag_doc_id": first.get("id"),
                "index_status": "ready",
                "status": "ready",
                "index_error": None,
                "last_status_sync_at": datetime.now().isoformat(),
            }
        elif remote_status == "FAILED":
            update = {
                "index_status": "failed",
                "status": "failed",
                "index_error": first.get("error_msg") or "LightRAG processing failed",
                "last_status_sync_at": datetime.now().isoformat(),
            }
        else:
            update = {"index_status": "processing", "status": "processing"}

        self.document_repository.update(doc_info["id"], update)
        return self.document_repository.get(doc_info["id"])

    async def list_documents(self, page: int, page_size: int) -> dict:
        try:
            documents = list(self._list_all_documents())
        except Exception:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

        hydrated = []
        for item in documents:
            try:
                hydrated.append(await self._sync_pending_document(item))
            except Exception:
                continue

        total = len(documents)
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "items": hydrated[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def delete_document(self, document_id: str) -> dict:
        doc_info = self.document_repository.get(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        synced = await self._sync_pending_document(doc_info)
        remote_id = synced.get("lightrag_doc_id")
        if remote_id:
            result = await self.lightrag_client.delete_documents([remote_id], delete_file=False, delete_llm_cache=False)
            status = result.get("status")
            if status not in {"deletion_started", "success", "not_found"}:
                raise AppServiceError(1004, result.get("message") or "远端删除失败")

        file_path = Path(synced.get("filepath") or "")
        if file_path.exists():
            file_path.unlink()
        self.document_repository.delete(document_id)
        return {"deleted": True, "id": document_id}
```

Modify `backend/api/document.py` so the endpoints await the service:

```python
@router.post("/upload", summary="上传文档")
async def upload_document(file: UploadFile = File(...)):
    doc_info = await document_service.upload(file.filename, file.file)
    return success(data=_build_document_response(doc_info), message="文档已提交到 LightRAG")


@router.get("/", summary="获取所有文档列表")
async def get_document_list(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=500)):
    page_data = await document_service.list_documents(page, page_size)
    items = [_build_document_response(doc) for doc in page_data.get("items", [])]
    return paginated(items=items, total=page_data.get("total", 0), page=page, page_size=page_size)


def _build_document_response(doc_info: dict) -> dict:
    payload = doc_info if isinstance(doc_info, dict) else {}
    return {
        "id": payload.get("id"),
        "filename": payload.get("filename"),
        "file_type": payload.get("file_type"),
        "created_at_iso": payload.get("created_at_iso"),
        "classification_result": payload.get("classification_result"),
        "file_available": payload.get("file_available", False),
        "index_status": payload.get("index_status") or payload.get("status"),
        "index_error": payload.get("index_error") or payload.get("error_message"),
        "lightrag_track_id": payload.get("lightrag_track_id"),
        "lightrag_doc_id": payload.get("lightrag_doc_id"),
    }
```

- [ ] **Step 4: Re-run the document service tests**

Run: `cd backend && python3 -m pytest test/test_document_service_lightrag.py test/test_document_empty_state.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the document upload/delete rewrite**

```bash
git add backend/app/infra/metadata_store.py \
  backend/app/infra/repositories/document_repository.py \
  backend/app/services/document_service.py \
  backend/api/document.py \
  backend/test/test_document_service_lightrag.py \
  backend/test/test_document_empty_state.py
git commit -m "feat: move document flow to lightrag"
```

### Task 3: Replace Startup Checks With LightRAG Health

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/test/test_main_block_index.py`

- [ ] **Step 1: Write the failing startup/health tests**

Replace `backend/test/test_main_block_index.py` with:

```python
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
MAIN_PATH = BACKEND_DIR / "main.py"


class _FakeFastAPIApp:
    def __init__(self, *args, **kwargs):
        self.middlewares = []

    def add_exception_handler(self, *args, **kwargs):
        return None

    def add_middleware(self, *args, **kwargs):
        self.middlewares.append((args, kwargs))

    def include_router(self, *args, **kwargs):
        return None

    def api_route(self, *args, **kwargs):
        return lambda fn: fn

    def get(self, *args, **kwargs):
        return lambda fn: fn


def _load_main_module(fake_client_cls):
    config_module = types.ModuleType("config")
    config_module.API_PREFIX = "/api/v1"
    config_module.DATA_DIR = Path("/tmp/docagent-backend/data")
    config_module.DOC_DIR = Path("/tmp/docagent-backend/doc")
    config_module.FILE_TYPE_DIRS = ["pdf"]
    config_module.DOUBAO_API_KEY = ""
    config_module.DOUBAO_DEFAULT_LLM_MODEL = "doubao-mini"
    config_module.LIGHTRAG_BASE_URL = "http://127.0.0.1:9621"

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = _FakeFastAPIApp
    fastapi_module.Request = object

    cors_module = types.ModuleType("fastapi.middleware.cors")
    cors_module.CORSMiddleware = object
    exceptions_module = types.ModuleType("fastapi.exceptions")
    exceptions_module.RequestValidationError = Exception
    responses_module = types.ModuleType("fastapi.responses")
    responses_module.RedirectResponse = object

    api_module = types.ModuleType("api")
    api_module.router = object()
    api_module.BusinessException = Exception
    api_module.business_exception_handler = lambda *args, **kwargs: None
    api_module.validation_exception_handler = lambda *args, **kwargs: None
    api_module.generic_exception_handler = lambda *args, **kwargs: None

    logger_module = types.ModuleType("app.core.logger")
    logger_module.logger = mock.Mock()
    logger_module.setup_logging = lambda *args, **kwargs: None
    logger_module.RequestContextMiddleware = type("RequestContextMiddleware", (), {})

    lightrag_client_module = types.ModuleType("app.infra.lightrag_client")
    lightrag_client_module.LightRAGClient = fake_client_cls

    spec = importlib.util.spec_from_file_location("main_under_test", str(MAIN_PATH))
    module = importlib.util.module_from_spec(spec)

    with mock.patch.dict(
        sys.modules,
        {
            "config": config_module,
            "fastapi": fastapi_module,
            "fastapi.middleware.cors": cors_module,
            "fastapi.exceptions": exceptions_module,
            "fastapi.responses": responses_module,
            "api": api_module,
            "app.core.logger": logger_module,
            "app.infra.lightrag_client": lightrag_client_module,
        },
        clear=False,
    ):
        spec.loader.exec_module(module)
        return module


def test_health_endpoint_reports_lightrag_check():
    class FakeLightRAGClient:
        async def health(self):
            return {"status": "healthy"}

    module = _load_main_module(FakeLightRAGClient)
    payload = module.health_check()
    if hasattr(payload, "__await__"):
        import asyncio
        payload = asyncio.run(payload)

    assert payload["checks"]["lightrag"] == "ok"


def test_default_wildcard_cors_disables_credentials(monkeypatch):
    class FakeLightRAGClient:
        async def health(self):
            return {"status": "healthy"}

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    module = _load_main_module(FakeLightRAGClient)
    cors_kwargs = module.app.middlewares[0][1]

    assert cors_kwargs["allow_origins"] == ["*"]
    assert cors_kwargs["allow_credentials"] is False
```

- [ ] **Step 2: Run the startup tests and verify they fail**

Run: `cd backend && python3 -m pytest test/test_main_block_index.py -v`

Expected: FAIL because `main.py` still imports vector store and block-index startup logic.

- [ ] **Step 3: Remove Chroma startup and replace it with LightRAG health**

Modify `backend/main.py` to use:

```python
from app.infra.lightrag_client import LightRAGClient


def _lightrag_client() -> LightRAGClient:
    return LightRAGClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("DocAgentRAG backend starting")
    logger.info("=" * 50)

    for dir_path in [DOC_DIR, DATA_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)

    for type_dir in FILE_TYPE_DIRS:
        (DOC_DIR / type_dir).mkdir(parents=True, exist_ok=True)

    sync_doubao_llm_availability(
        doubao_api_key=DOUBAO_API_KEY,
        doubao_default_llm_model=DOUBAO_DEFAULT_LLM_MODEL,
        config_module=_config,
        logger_instance=logger,
    )

    try:
        health = await _lightrag_client().health()
        app.state.lightrag_health = health
        logger.info("LightRAG health ok: {}", health.get("status", "unknown"))
    except Exception as exc:
        app.state.lightrag_health = {"status": "unhealthy", "detail": str(exc)}
        logger.warning("LightRAG health check failed: {}", exc)

    yield

    logger.info("系统正在关闭...")


@app.get("/health", summary="健康检查")
async def health_check():
    health = getattr(app.state, "lightrag_health", {"status": "unknown"})
    lightrag_ok = health.get("status") == "healthy"
    return {
        "status": "healthy" if lightrag_ok else "degraded",
        "version": "1.0.0",
        "checks": {
            "lightrag": "ok" if lightrag_ok else "failed"
        },
    }
```

Delete imports and calls related to:

- `app.infra.embedding_provider`
- `app.infra.vector_store`
- `app.services.indexing_service`
- `check_and_rebuild_block_indexes()`
- `detect_and_lock_embedding_dim()`

- [ ] **Step 4: Re-run the startup tests**

Run: `cd backend && python3 -m pytest test/test_main_block_index.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the startup simplification**

```bash
git add backend/main.py backend/test/test_main_block_index.py
git commit -m "refactor: replace startup block checks with lightrag health"
```

### Task 4: Rewrite RetrievalService And `/retrieval/query`

**Files:**
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/api/retrieval.py`
- Create: `backend/test/test_retrieval_service_lightrag.py`

- [ ] **Step 1: Write the failing retrieval tests**

Create `backend/test/test_retrieval_service_lightrag.py` with:

```python
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.retrieval_service import RetrievalService


class FakeLightRAGClient:
    async def query_data(self, text: str, mode: str, top_k: int):
        return {
            "status": "success",
            "message": "ok",
            "data": {
                "entities": [
                    {
                        "entity_name": "预算审批",
                        "entity_type": "PROCESS",
                        "description": "预算流转节点",
                        "file_path": "/docs/budget.pdf",
                        "reference_id": "1",
                    }
                ],
                "relationships": [
                    {
                        "src_id": "预算",
                        "tgt_id": "审批",
                        "description": "预算需要审批",
                        "keywords": "预算,审批",
                        "weight": 0.91,
                        "file_path": "/docs/budget.pdf",
                        "reference_id": "1",
                    }
                ],
                "chunks": [
                    {
                        "content": "预算审批流程包括提交、复核和归档。",
                        "file_path": "/docs/budget.pdf",
                        "chunk_id": "chunk-1",
                        "reference_id": "1",
                    }
                ],
                "references": [{"reference_id": "1", "file_path": "/docs/budget.pdf"}],
            },
            "metadata": {"query_mode": "hybrid"},
        }


def test_query_normalizes_lightrag_data():
    service = RetrievalService(lightrag_client=FakeLightRAGClient())

    payload = asyncio.run(service.query("预算审批", "hybrid", top_k=5))

    assert payload["mode_used"] == "hybrid"
    assert [item["kind"] for item in payload["results"]] == ["chunk", "relationship", "entity"]
    assert payload["results"][0]["chunk_id"] == "chunk-1"
    assert payload["references"][0]["file_path"] == "/docs/budget.pdf"
```

Append this API test to the same file:

```python
def test_query_api_returns_service_payload(monkeypatch):
    import api.retrieval as retrieval_api

    async def fake_query(text, mode, top_k):
        return {"query": text, "mode_used": mode, "results": [], "references": [], "metadata": {}}

    monkeypatch.setattr(retrieval_api.retrieval_service, "query", fake_query)

    request = retrieval_api.LightRAGQueryRequest(query="预算审批", mode="hybrid", top_k=5)
    body = asyncio.run(retrieval_api.query_api(request))

    assert body["code"] == 200
    assert body["data"]["mode_used"] == "hybrid"
```

- [ ] **Step 2: Run the retrieval tests and verify they fail**

Run: `cd backend && python3 -m pytest test/test_retrieval_service_lightrag.py -v`

Expected: FAIL because `RetrievalService` and `api.retrieval` still expose the old workspace-search contract.

- [ ] **Step 3: Replace the retrieval service and route contract**

Rewrite `backend/app/services/retrieval_service.py` around:

```python
from app.infra.lightrag_client import LightRAGClient
from app.infra.repositories.document_repository import DocumentRepository
from app.services.errors import AppServiceError
from config import DATA_DIR, LIGHTRAG_QUERY_MODE_DEFAULT


ALLOWED_QUERY_MODES = {"naive", "local", "global", "hybrid", "mix", "bypass"}


class RetrievalService:
    def __init__(self, lightrag_client=None, document_repository=None):
        self.lightrag_client = lightrag_client or LightRAGClient()
        self.document_repository = document_repository or DocumentRepository(data_dir=DATA_DIR)

    @staticmethod
    def _normalize_chunk(chunk: dict) -> dict:
        return {
            "kind": "chunk",
            "title": chunk.get("file_path") or "chunk",
            "content": chunk.get("content") or "",
            "file_path": chunk.get("file_path"),
            "reference_id": chunk.get("reference_id"),
            "chunk_id": chunk.get("chunk_id"),
        }

    @staticmethod
    def _normalize_relationship(item: dict) -> dict:
        return {
            "kind": "relationship",
            "title": f"{item.get('src_id', '')} -> {item.get('tgt_id', '')}",
            "content": item.get("description") or "",
            "file_path": item.get("file_path"),
            "reference_id": item.get("reference_id"),
            "keywords": item.get("keywords"),
            "weight": item.get("weight"),
        }

    @staticmethod
    def _normalize_entity(item: dict) -> dict:
        return {
            "kind": "entity",
            "title": item.get("entity_name") or "",
            "content": item.get("description") or "",
            "entity_type": item.get("entity_type"),
            "file_path": item.get("file_path"),
            "reference_id": item.get("reference_id"),
        }

    async def query(self, query: str, mode: str, top_k: int = 10) -> dict:
        normalized_mode = (mode or LIGHTRAG_QUERY_MODE_DEFAULT).strip().lower()
        if normalized_mode not in ALLOWED_QUERY_MODES:
            raise AppServiceError(3002, f"不支持的检索模式: {mode}")

        payload = await self.lightrag_client.query_data(query, normalized_mode, top_k)
        data = payload.get("data") or {}

        results = []
        results.extend(self._normalize_chunk(item) for item in data.get("chunks") or [])
        results.extend(self._normalize_relationship(item) for item in data.get("relationships") or [])
        results.extend(self._normalize_entity(item) for item in data.get("entities") or [])

        return {
            "query": query,
            "mode_used": normalized_mode,
            "results": results,
            "references": data.get("references") or [],
            "metadata": payload.get("metadata") or {},
        }

    def stats(self) -> dict:
        docs = self.document_repository.list_all()
        return {
            "total_documents": len(docs),
            "ready_documents": sum(1 for item in docs if (item.get("index_status") or item.get("status")) == "ready"),
            "failed_documents": sum(1 for item in docs if (item.get("index_status") or item.get("status")) == "failed"),
        }
```

Replace `backend/api/retrieval.py` with:

```python
from fastapi import APIRouter
from pydantic import BaseModel, Field

from api import BusinessException, success
from app.services.errors import AppServiceError
from app.services.retrieval_service import RetrievalService


router = APIRouter()
retrieval_service = RetrievalService()


class LightRAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: str = "hybrid"
    top_k: int = Field(10, ge=1, le=100)


@router.post("/query", summary="LightRAG structured retrieval")
async def query_api(request: LightRAGQueryRequest):
    try:
        payload = await retrieval_service.query(request.query, request.mode, request.top_k)
        return success(data=payload)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/stats", summary="文档统计")
async def get_document_stats_api():
    return success(data=retrieval_service.stats())
```

- [ ] **Step 4: Re-run the retrieval tests**

Run: `cd backend && python3 -m pytest test/test_retrieval_service_lightrag.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the retrieval rewrite**

```bash
git add backend/app/services/retrieval_service.py \
  backend/api/retrieval.py \
  backend/test/test_retrieval_service_lightrag.py
git commit -m "feat: route retrieval through lightrag query data"
```

### Task 5: Rewrite QA Service And SSE Proxying

**Files:**
- Modify: `backend/app/services/qa_service.py`
- Modify: `backend/api/qa.py`
- Modify: `backend/app/schemas/qa.py`
- Create: `backend/test/test_qa_service_lightrag.py`

- [ ] **Step 1: Write the failing QA tests**

Create `backend/test/test_qa_service_lightrag.py` with:

```python
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import connect_sqlite
from app.infra.repositories.qa_session_repository import QASessionRepository
from app.services.qa_service import QAService


class FakeLightRAGClient:
    async def query(self, text: str, mode: str, include_references: bool = True, include_chunk_content: bool = True):
        return {
            "response": "预算审批流程包括提交、复核和归档。",
            "references": [{"reference_id": "1", "file_path": "/docs/budget.pdf"}],
        }

    async def query_stream(self, text: str, mode: str):
        yield json.dumps({"references": [{"reference_id": "1", "file_path": "/docs/budget.pdf"}]})
        yield json.dumps({"response": "预算审批流程"})
        yield json.dumps({"response": "包括提交和复核"})


def _create_repo(tmp_path: Path) -> QASessionRepository:
    db_path = tmp_path / "docagent.db"
    with connect_sqlite(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE qa_sessions (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                doc_ids TEXT NOT NULL,
                answer TEXT NOT NULL,
                citations TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    return QASessionRepository(db_path=db_path, data_dir=tmp_path)


def test_answer_uses_lightrag_hybrid_mode_and_persists_session(tmp_path: Path):
    service = QAService(lightrag_client=FakeLightRAGClient())
    service.qa_session_repo = _create_repo(tmp_path)

    payload = asyncio.run(service.answer("预算审批是什么", session_id="sess-1"))

    assert payload["answer"].startswith("预算审批流程")
    assert payload["citations"][0]["file_path"] == "/docs/budget.pdf"
    assert service.qa_session_repo.get("sess-1")["citations"][0]["file_path"] == "/docs/budget.pdf"


def test_answer_stream_emits_references_and_chunks():
    service = QAService(lightrag_client=FakeLightRAGClient())

    async def _collect():
        items = []
        async for item in service.answer_stream("预算审批是什么", session_id="sess-1"):
            items.append(item)
        return items

    items = asyncio.run(_collect())

    assert items[0]["type"] == "references"
    assert items[1]["type"] == "chunk"
    assert items[1]["chunk"] == "预算审批流程"
```

- [ ] **Step 2: Run the QA tests and verify they fail**

Run: `cd backend && python3 -m pytest test/test_qa_service_lightrag.py -v`

Expected: FAIL because `QAService` still depends on `gateway`, `qa_chain`, and old retrieval blocks.

- [ ] **Step 3: Implement LightRAG-backed QA**

Modify `backend/app/schemas/qa.py` citation model to support file-path references:

```python
class Citation(BaseModel):
    doc_id: str | None = None
    file_path: str | None = None
    filename: str | None = None
    reference_id: str | None = None
    section: str | None = None
    excerpt: str | None = None
```

Rewrite `backend/app/services/qa_service.py` around:

```python
import json
from pathlib import Path

from app.infra.lightrag_client import LightRAGClient
from app.infra.repositories.qa_session_repository import QASessionRepository


class QAService:
    def __init__(self, lightrag_client=None):
        self.lightrag_client = lightrag_client or LightRAGClient()
        self.qa_session_repo = QASessionRepository()

    @staticmethod
    def _normalize_references(references: list[dict]) -> list[dict]:
        normalized = []
        for item in references or []:
            file_path = item.get("file_path")
            normalized.append({
                "doc_id": item.get("reference_id"),
                "reference_id": item.get("reference_id"),
                "file_path": file_path,
                "filename": Path(file_path).name if file_path else item.get("reference_id"),
            })
        return normalized

    async def answer(self, query: str, doc_ids=None, top_k: int = 8, session_id: str | None = None) -> dict:
        payload = await self.lightrag_client.query(
            query,
            mode="hybrid",
            include_references=True,
            include_chunk_content=True,
        )
        citations = self._normalize_references(payload.get("references") or [])
        answer = payload.get("response") or "未找到相关答案。"

        if session_id:
            persisted_doc_ids = doc_ids or [item.get("file_path") for item in citations if item.get("file_path")]
            self.qa_session_repo.save(query, persisted_doc_ids, answer, citations, session_id=session_id)

        return {
            "query": query,
            "answer": answer,
            "citations": citations,
            "confidence": 0.5 if citations else 0.0,
            "session_id": session_id,
        }

    async def answer_stream(self, query: str, doc_ids=None, session_id: str | None = None, top_k: int = 8):
        chunks = []
        references = []

        async for line in self.lightrag_client.query_stream(query, mode="hybrid"):
            if not line:
                continue
            data = json.loads(line)
            if "references" in data:
                references = self._normalize_references(data["references"])
                yield {"type": "references", "references": references}
            elif "response" in data:
                chunks.append(data["response"])
                yield {"type": "chunk", "chunk": data["response"]}
            elif "error" in data:
                yield {"type": "error", "error": data["error"]}
                return

        if session_id:
            persisted_doc_ids = doc_ids or [item.get("file_path") for item in references if item.get("file_path")]
            self.qa_session_repo.save(query, persisted_doc_ids, "".join(chunks), references, session_id=session_id)
```

Modify `backend/api/qa.py` stream generator to convert service events into SSE:

```python
@router.post("/stream", summary="流式文档问答")
async def answer_question_stream(request: QARequest):
    session_id = request.session_id or str(uuid4())

    async def generate():
        async for item in qa_service.answer_stream(
            query=request.query,
            doc_ids=request.doc_ids,
            session_id=session_id,
            top_k=request.top_k,
        ):
            if item["type"] == "references":
                yield f"data: {json.dumps({'references': item['references']}, ensure_ascii=False)}\\n\\n"
            elif item["type"] == "chunk":
                yield f"data: {json.dumps({'chunk': item['chunk']}, ensure_ascii=False)}\\n\\n"
            elif item["type"] == "error":
                yield f"data: {json.dumps({'error': item['error'], 'session_id': session_id}, ensure_ascii=False)}\\n\\n"
                return

        yield f"data: {json.dumps({'status': 'complete', 'session_id': session_id}, ensure_ascii=False)}\\n\\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: Re-run the QA tests**

Run: `cd backend && python3 -m pytest test/test_qa_service_lightrag.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the QA proxy rewrite**

```bash
git add backend/app/services/qa_service.py \
  backend/api/qa.py \
  backend/app/schemas/qa.py \
  backend/test/test_qa_service_lightrag.py
git commit -m "feat: proxy qa through lightrag"
```

### Task 6: Add LightRAG Graph Endpoints

**Files:**
- Modify: `backend/api/topics.py`
- Create: `backend/test/test_topics_lightrag.py`

- [ ] **Step 1: Write the failing graph endpoint tests**

Create `backend/test/test_topics_lightrag.py` with:

```python
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.topics as topics_api


class FakeLightRAGClient:
    async def list_graph_labels(self):
        return ["预算审批", "合同管理"]

    async def get_graph(self, label: str, max_depth: int = 3, max_nodes: int = 1000):
        return {
            "nodes": [
                {"id": "n1", "labels": ["预算审批"], "properties": {"degree": 3}},
                {"id": "n2", "labels": ["复核"], "properties": {"degree": 1}},
            ],
            "edges": [
                {"id": "e1", "type": "related", "source": "n1", "target": "n2", "properties": {"description": "预算需要复核"}}
            ],
            "is_truncated": False,
        }


def test_labels_endpoint_returns_label_list(monkeypatch):
    monkeypatch.setattr(topics_api, "lightrag_client", FakeLightRAGClient())

    body = asyncio.run(topics_api.get_graph_labels())

    assert body["code"] == 200
    assert body["data"]["items"] == ["预算审批", "合同管理"]


def test_graph_endpoint_returns_lightrag_graph(monkeypatch):
    monkeypatch.setattr(topics_api, "lightrag_client", FakeLightRAGClient())

    body = asyncio.run(topics_api.get_knowledge_graph(label="预算审批", max_depth=2, max_nodes=50))

    assert body["code"] == 200
    assert body["data"]["nodes"][0]["labels"] == ["预算审批"]
    assert body["data"]["edges"][0]["source"] == "n1"
```

- [ ] **Step 2: Run the graph tests and verify they fail**

Run: `cd backend && python3 -m pytest test/test_topics_lightrag.py -v`

Expected: FAIL because `api.topics` still depends on `GraphIndex`, `GraphStore`, and entity repositories.

- [ ] **Step 3: Replace the topics API with LightRAG proxies**

Rewrite `backend/api/topics.py` around:

```python
from fastapi import APIRouter, Query

from api import BusinessException, success
from app.core.logger import logger
from app.infra.lightrag_client import LightRAGClient
from app.services.errors import AppServiceError


router = APIRouter()
lightrag_client = LightRAGClient()


@router.get("/labels", summary="获取图谱标签")
async def get_graph_labels():
    try:
        labels = await lightrag_client.list_graph_labels()
        return success(data={"items": labels}, message="获取标签成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/graph", summary="获取知识图谱数据")
async def get_knowledge_graph(
    label: str = Query(..., description="图谱起点标签"),
    max_depth: int = Query(3, ge=1),
    max_nodes: int = Query(1000, ge=1),
):
    try:
        graph = await lightrag_client.get_graph(label, max_depth=max_depth, max_nodes=max_nodes)
        return success(data=graph, message="获取知识图谱成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)
```

Also add these methods to `backend/app/infra/lightrag_client.py`:

```python
    async def list_graph_labels(self) -> list[str]:
        response = await self._request("GET", "/graph/label/list")
        return response.json()

    async def get_graph(self, label: str, max_depth: int = 3, max_nodes: int = 1000) -> dict[str, Any]:
        response = await self._request(
            "GET",
            "/graphs",
            params={"label": label, "max_depth": max_depth, "max_nodes": max_nodes},
        )
        return response.json()
```

- [ ] **Step 4: Re-run the graph tests**

Run: `cd backend && python3 -m pytest test/test_topics_lightrag.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the graph API rewrite**

```bash
git add backend/api/topics.py \
  backend/app/infra/lightrag_client.py \
  backend/test/test_topics_lightrag.py
git commit -m "feat: proxy graph endpoints through lightrag"
```

### Task 7: Simplify Frontend API Layer, Documents Page, And Search Page

**Files:**
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/components/FileUpload.vue`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Create: `frontend/docagent-frontend/src/components/LightRagResultList.vue`

- [ ] **Step 1: Replace the frontend API surface with LightRAG-first methods**

Modify `frontend/docagent-frontend/src/api/index.js` to expose:

```javascript
export const api = {
  uploadDocument: (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
      onUploadProgress: onProgress,
    })
  },
  getDocumentList: (page = 1, pageSize = 100) => {
    return request.get('/documents/', { params: { page, page_size: pageSize } })
  },
  deleteDocument: (documentId) => {
    return request.delete(`/documents/${documentId}`)
  },
  lightragQueryData: (payload) => {
    return request.post('/retrieval/query', payload)
  },
  lightRagQA: (payload) => {
    return request.post('/qa/', payload)
  },
  streamLightRagQA: (payload, handlers = {}) => {
    const ctrl = new AbortController()

    fetch('/api/v1/qa/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          const text = await res.text().catch(() => '')
          throw new Error(`HTTP ${res.status}: ${text}`)
        }

        const reader = res.body?.getReader?.()
        if (!reader) throw new Error('QA stream is unavailable')

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split('\\n\\n')
          buffer = frames.pop() ?? ''

          for (const frame of frames) {
            const dataLine = frame.split('\\n').find((line) => line.startsWith('data: '))
            if (!dataLine) continue
            const parsed = JSON.parse(dataLine.slice(6))
            if (parsed.references) handlers.onReferences?.(parsed.references)
            else if (parsed.error) handlers.onError?.(new Error(parsed.error))
            else if (parsed.status === 'complete') handlers.onDone?.(parsed)
            else handlers.onMessage?.(parsed)
          }
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') handlers.onError?.(error)
      })

    return () => ctrl.abort()
  },
  getGraph: (params = {}) => request.get('/topics/graph', { params }),
  getGraphLabels: () => request.get('/topics/labels'),
}
```

- [ ] **Step 2: Update upload and document list UX**

Modify `frontend/docagent-frontend/src/components/FileUpload.vue`:

```javascript
await api.uploadDocument(file.raw, (evt) => {
  if (evt.total) {
    uploadPercent.value = Math.round((evt.loaded / evt.total) * 100)
  }
})
uploadPercent.value = 100
lastResult.value = { success: true, message: `${file.name} 已提交到 LightRAG，正在索引` }
```

Modify `frontend/docagent-frontend/src/components/FileList.vue` to add index status rendering:

```vue
<el-table-column label="索引状态" width="140">
  <template #default="{ row }">
    <el-tag :type="statusTagType(row.index_status)">
      {{ formatIndexStatus(row.index_status) }}
    </el-tag>
  </template>
</el-table-column>
```

Add helpers:

```javascript
const formatIndexStatus = (status) => ({
  queued: '已排队',
  processing: '处理中',
  ready: '可检索',
  failed: '失败',
  duplicated: '已存在',
}[status] || '未知')

const statusTagType = (status) => ({
  queued: 'info',
  processing: 'warning',
  ready: 'success',
  failed: 'danger',
  duplicated: 'info',
}[status] || 'info')
```

Modify `frontend/docagent-frontend/src/pages/DocumentsPage.vue` so the header copy and metrics reflect indexing rather than classification:

```javascript
const readyCount = computed(
  () => documentList.value.filter(item => item.index_status === 'ready').length
)

const failedCount = computed(
  () => documentList.value.filter(item => item.index_status === 'failed').length
)
```

- [ ] **Step 3: Replace SearchPage with a LightRAG result page**

Create `frontend/docagent-frontend/src/components/LightRagResultList.vue` with:

```vue
<template>
  <div class="result-stack">
    <article
      v-for="(item, index) in results"
      :key="`${item.kind}-${item.reference_id || index}`"
      class="result-card"
    >
      <div class="result-head">
        <span class="badge badge-gray">{{ item.kind }}</span>
        <strong>{{ item.title }}</strong>
      </div>
      <p class="result-content">{{ item.content }}</p>
      <small v-if="item.file_path">{{ item.file_path }}</small>
    </article>
  </div>
</template>

<script setup>
defineProps({
  results: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
</script>
```

Rewrite `frontend/docagent-frontend/src/pages/SearchPage.vue` around:

```vue
<script setup>
import { ref } from 'vue'

import LightRagResultList from '@/components/LightRagResultList.vue'
import { api } from '@/api'

const query = ref('')
const mode = ref('hybrid')
const topK = ref(10)
const loading = ref(false)
const error = ref('')
const results = ref([])
const references = ref([])

const runQuery = async () => {
  if (!query.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    const response = await api.lightragQueryData({
      query: query.value.trim(),
      mode: mode.value,
      top_k: topK.value,
    })
    results.value = response.data?.results || []
    references.value = response.data?.references || []
  } catch (err) {
    error.value = err.message || '检索失败'
    results.value = []
    references.value = []
  } finally {
    loading.value = false
  }
}
</script>
```

Use exactly these mode options in the template:

```vue
<option value="naive">naive</option>
<option value="local">local</option>
<option value="global">global</option>
<option value="hybrid">hybrid</option>
<option value="mix">mix</option>
```

- [ ] **Step 4: Build the frontend and verify it passes**

Run: `cd frontend/docagent-frontend && npm run build`

Expected: PASS and Vite writes the production bundle without references to `workspaceSearch`, `DocumentReader`, or `SearchToolbar`.

- [ ] **Step 5: Commit the frontend search/documents update**

```bash
git add frontend/docagent-frontend/src/api/index.js \
  frontend/docagent-frontend/src/components/FileUpload.vue \
  frontend/docagent-frontend/src/components/FileList.vue \
  frontend/docagent-frontend/src/components/LightRagResultList.vue \
  frontend/docagent-frontend/src/pages/DocumentsPage.vue \
  frontend/docagent-frontend/src/pages/SearchPage.vue
git commit -m "feat: update documents and search for lightrag"
```

### Task 8: Update QA Page, Graph Page, And Citation Display

**Files:**
- Modify: `frontend/docagent-frontend/src/pages/QAPage.vue`
- Modify: `frontend/docagent-frontend/src/components/QASessionPanel.vue`
- Modify: `frontend/docagent-frontend/src/pages/GraphPage.vue`

- [ ] **Step 1: Remove document-scope selection from QAPage**

Rewrite `frontend/docagent-frontend/src/pages/QAPage.vue` to use a global question box:

```vue
<script setup>
import { onBeforeUnmount, ref } from 'vue'

import QASessionPanel from '@/components/QASessionPanel.vue'
import { api } from '@/api'

const question = ref('')
const answer = ref('')
const citations = ref([])
const error = ref('')
const loading = ref(false)
const sessionId = ref('')
let cancelStream = null

const submitQuestion = () => {
  if (!question.value.trim()) return

  cancelStream?.()
  answer.value = ''
  citations.value = []
  error.value = ''
  sessionId.value = ''
  loading.value = true

  cancelStream = api.streamLightRagQA(
    { query: question.value.trim() },
    {
      onReferences(items) {
        citations.value = items
      },
      onMessage(payload) {
        answer.value += payload.chunk || ''
      },
      onDone(payload) {
        sessionId.value = payload.session_id || ''
        loading.value = false
      },
      onError(streamError) {
        error.value = streamError.message || '问答请求失败'
        loading.value = false
      },
    }
  )
}

onBeforeUnmount(() => cancelStream?.())
</script>
```

Modify the copy in the template from “先选择文档范围” to “系统会基于 LightRAG 全局知识库回答问题” and remove the document chip list entirely.

- [ ] **Step 2: Make citations render file paths**

Modify `frontend/docagent-frontend/src/components/QASessionPanel.vue` to render:

```vue
<span
  v-for="citation in citations"
  :key="citation.reference_id || citation.file_path || citation.doc_id"
  class="citation-chip"
>
  {{ citation.filename || citation.file_path || citation.doc_id }}
</span>
```

- [ ] **Step 3: Replace graph document filtering with label-based lookup**

Rewrite `frontend/docagent-frontend/src/pages/GraphPage.vue` to load labels first and map LightRAG graph types:

```vue
<script setup>
import { computed, onMounted, ref } from 'vue'

import GraphCanvas from '@/components/GraphCanvas.vue'
import { api } from '@/api'

const labels = ref([])
const selectedLabel = ref('')
const rawGraph = ref({ nodes: [], edges: [] })
const selectedNodeId = ref('')
const loading = ref(false)
const error = ref('')

const nodes = computed(() => (
  (rawGraph.value.nodes || []).map((node) => ({
    id: node.id,
    label: node.labels?.[0] || node.id,
    degree: node.properties?.degree || 0,
  }))
))

const edges = computed(() => (
  (rawGraph.value.edges || []).map((edge) => ({
    from: edge.source,
    to: edge.target,
    label: edge.type || edge.properties?.description || 'related',
    doc_id: edge.properties?.source_id || '',
  }))
))

const selectedNode = computed(() => (
  nodes.value.find((node) => node.id === selectedNodeId.value) || null
))

const relatedEdges = computed(() => (
  edges.value.filter((edge) => edge.from === selectedNodeId.value || edge.to === selectedNodeId.value)
))

const loadLabels = async () => {
  const response = await api.getGraphLabels()
  labels.value = response.data?.items || []
  selectedLabel.value = labels.value[0] || ''
}

const loadGraph = async () => {
  if (!selectedLabel.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await api.getGraph({ label: selectedLabel.value, max_depth: 3, max_nodes: 200 })
    rawGraph.value = response.data || { nodes: [], edges: [] }
    selectedNodeId.value = nodes.value[0]?.id || ''
  } catch (graphError) {
    error.value = graphError.message || '图谱加载失败'
    rawGraph.value = { nodes: [], edges: [] }
    selectedNodeId.value = ''
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadLabels()
  await loadGraph()
})
</script>
```

Update the template so the label control is:

```vue
<select v-model="selectedLabel" class="filter-input" @change="loadGraph">
  <option v-for="label in labels" :key="label" :value="label">{{ label }}</option>
</select>
```

Keep the right-side detail panel bound to `selectedNode` and `relatedEdges`, and keep the left-side `GraphCanvas` call as:

```vue
<GraphCanvas
  :nodes="nodes"
  :edges="edges"
  :selected-node-id="selectedNodeId"
  @select-node="selectedNodeId = $event"
/>
```

- [ ] **Step 4: Build the frontend and verify it passes**

Run: `cd frontend/docagent-frontend && npm run build`

Expected: PASS and the build contains no `streamQA(` call sites or `doc scope` markup in `QAPage.vue`.

- [ ] **Step 5: Commit the frontend QA/graph update**

```bash
git add frontend/docagent-frontend/src/pages/QAPage.vue \
  frontend/docagent-frontend/src/components/QASessionPanel.vue \
  frontend/docagent-frontend/src/pages/GraphPage.vue
git commit -m "feat: align qa and graph pages with lightrag"
```

### Task 9: Delete Legacy Code, Remove Old Dependencies, And Run Final Verification

**Files:**
- Delete: `backend/utils/block_extractor.py`
- Delete: `backend/utils/retriever.py`
- Delete: `backend/utils/smart_retrieval.py`
- Delete: `backend/app/infra/vector_store.py`
- Delete: `backend/app/infra/embedding_provider.py`
- Delete: `backend/app/domain/llm/qa_chain.py`
- Delete: `backend/app/domain/llm/gateway.py`
- Delete: `backend/app/services/topic_tree_service.py`
- Delete: `backend/app/services/indexing_service.py`
- Delete: `backend/app/services/document_vector_index_service.py`
- Delete: `backend/app/services/ingest_pipeline.py`
- Delete: `backend/test/test_retriever.py`
- Delete: `backend/test/test_storage.py`
- Delete: `backend/test/test_indexing_service.py`
- Delete: `backend/test/test_document_reader_api.py`
- Delete: `backend/test/test_backfill_block_index.py`
- Delete: `backend/test/test_block_extractor.py`
- Delete: `backend/test/test_topic_tree_service.py`
- Delete: `backend/test/test_topic_labeler_and_embedding_provider.py`
- Delete: `frontend/docagent-frontend/src/pages/TaxonomyPage.vue`
- Delete: `frontend/docagent-frontend/src/composables/useSearch.js`
- Delete: `frontend/docagent-frontend/src/composables/useDocumentReader.js`
- Delete: `frontend/docagent-frontend/src/composables/useSummary.js`
- Delete: `frontend/docagent-frontend/src/components/ClassificationPanel.vue`
- Delete: `frontend/docagent-frontend/src/components/DocumentReader.vue`
- Delete: `frontend/docagent-frontend/src/components/TopicTreePanel.vue`
- Delete: `frontend/docagent-frontend/src/components/SummaryDrawer.vue`
- Delete: `frontend/docagent-frontend/src/components/ClassificationReportDrawer.vue`
- Delete: `frontend/docagent-frontend/src/components/SearchToolbar.vue`
- Delete: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- Delete: `frontend/docagent-frontend/src/components/__tests__/TopicTreePanel.spec.js`
- Delete: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`
- Delete: `frontend/docagent-frontend/src/components/__tests__/DocumentReader.spec.js`
- Delete: `frontend/docagent-frontend/src/components/__tests__/SearchToolbar.spec.js`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Remove legacy Python dependencies**

Edit `backend/requirements.txt` to remove:

```text
chromadb
rank_bm25
sentence-transformers
```

Keep:

```text
httpx>=0.27,<0.29
fastapi
uvicorn
pytest
```

- [ ] **Step 2: Delete unused backend/frontend modules**

Delete the exact files listed above. Use `apply_patch` deletes for tracked files so the diff is explicit.

- [ ] **Step 3: Verify no live references remain**

Run:

```bash
rg -n "block_extractor|smart_retrieval|utils\\.retriever|qa_chain|gateway|vector_store|DocumentReader|TopicTreePanel|SummaryDrawer|ClassificationReportDrawer|SearchToolbar|DocumentResultList" backend frontend/docagent-frontend/src
```

Expected: no matches in live source files. Test fixtures or plan/spec docs may still contain the strings.

- [ ] **Step 4: Run the final verification suite**

Run:

```bash
cd backend && python3 -m pytest \
  test/test_lightrag_client.py \
  test/test_document_service_lightrag.py \
  test/test_retrieval_service_lightrag.py \
  test/test_qa_service_lightrag.py \
  test/test_topics_lightrag.py \
  test/test_document_empty_state.py \
  test/test_main_block_index.py -v
```

Run:

```bash
cd frontend/docagent-frontend && npm run build
```

Expected:

- backend targeted suite PASS
- frontend build PASS
- no imports remain to deleted legacy modules

- [ ] **Step 5: Commit the cleanup and verification**

```bash
git add backend/requirements.txt \
  backend \
  frontend/docagent-frontend/src
git commit -m "refactor: complete lightrag centric migration"
```
