# DocAgent Modular Foundation And Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the bootstrap, platform, LightRAG gateway, legacy adapter, and worker scaffolding needed for the modular architecture while keeping the existing backend bootable and current v1 routes available.

**Architecture:** Add the new structure beside the current code first. The application factory, settings, shared primitives, LightRAG gateway, and legacy adapters become the only approved extension points for future work. Existing services may still run during this stage, but the repository gains the architectural guardrails that later plans depend on.

**Tech Stack:** FastAPI, Pydantic Settings, sqlite3, httpx, pytest

---

## File Structure

**Files:**
- Create: `backend/app/bootstrap/settings.py`
- Create: `backend/app/bootstrap/app_factory.py`
- Create: `backend/app/bootstrap/router.py`
- Create: `backend/app/bootstrap/lifespan.py`
- Create: `backend/app/bootstrap/deps.py`
- Create: `backend/app/platform/errors.py`
- Create: `backend/app/platform/result.py`
- Create: `backend/app/platform/events.py`
- Create: `backend/app/platform/task_queue.py`
- Create: `backend/app/platform/telemetry.py`
- Create: `backend/app/platform/sqlite.py`
- Create: `backend/app/adapters/lightrag/gateway.py`
- Create: `backend/app/adapters/lightrag/schemas.py`
- Create: `backend/app/adapters/lightrag/mappers.py`
- Create: `backend/app/adapters/legacy/document_processor_adapter.py`
- Create: `backend/app/adapters/legacy/retriever_adapter.py`
- Create: `backend/app/adapters/legacy/smart_retrieval_adapter.py`
- Create: `backend/api/v2/__init__.py`
- Create: `backend/api/v2/runtime.py`
- Create: `backend/worker.py`
- Modify: `backend/main.py`
- Modify: `backend/config.py`
- Modify: `backend/app/infra/lightrag_client.py`
- Create: `backend/test/test_bootstrap_app_factory.py`
- Create: `backend/test/test_lightrag_gateway_v2.py`
- Create: `backend/test/test_legacy_adapter_boundaries.py`

---

### Task 1: Create Settings, App Factory, And v2 Router Shell

**Files:**
- Create: `backend/test/test_bootstrap_app_factory.py`
- Create: `backend/app/bootstrap/settings.py`
- Create: `backend/app/bootstrap/app_factory.py`
- Create: `backend/app/bootstrap/router.py`
- Create: `backend/app/bootstrap/lifespan.py`
- Modify: `backend/main.py`
- Modify: `backend/config.py`

- [ ] **Step 1: Write the failing bootstrap tests**

Create `backend/test/test_bootstrap_app_factory.py` with:

```python
from fastapi.testclient import TestClient

from app.bootstrap.app_factory import create_app
from app.bootstrap.settings import Settings


def test_create_app_registers_v1_and_v2_routes():
    app = create_app(Settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    paths = {route.path for route in app.routes}
    assert "/api/v1/documents/" in paths or "/api/v1/documents" in paths
    assert "/api/v2/runtime/health" in paths
```

- [ ] **Step 2: Run the bootstrap test and verify it fails**

Run: `cd backend && python -m pytest test/test_bootstrap_app_factory.py::test_create_app_registers_v1_and_v2_routes -v`
Expected: FAIL because `app.bootstrap` and `/api/v2/runtime/health` do not exist yet.

- [ ] **Step 3: Implement the settings object and app factory**

Create `backend/app/bootstrap/settings.py` with:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    base_dir: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    doc_dir: Path = Path(__file__).resolve().parents[2] / "doc"
    api_v1_prefix: str = "/api/v1"
    api_v2_prefix: str = "/api/v2"
    serve_frontend_dist: bool = False
    lightrag_base_url: str = "http://127.0.0.1:9621"
    local_embedding_base_url: str = "http://127.0.0.1:8011"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

Create `backend/app/bootstrap/router.py` with:

```python
from fastapi import APIRouter

from api import router as v1_router
from api.v2 import router as v2_router


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(v1_router, prefix="/api/v1")
    router.include_router(v2_router, prefix="/api/v2")
    return router
```

Create `backend/app/bootstrap/app_factory.py` with:

```python
from fastapi import FastAPI

from app.bootstrap.lifespan import lifespan
from app.bootstrap.router import build_api_router
from app.bootstrap.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(title="DocAgent", lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(build_api_router())
    return app
```

Create `backend/api/v2/runtime.py` with:

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "layer": "runtime"}
```

Create `backend/api/v2/__init__.py` with:

```python
from fastapi import APIRouter

from .runtime import router as runtime_router

router = APIRouter()
router.include_router(runtime_router, prefix="/runtime", tags=["runtime"])
```

Update `backend/main.py` to:

```python
from app.bootstrap.app_factory import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=6008)
```

- [ ] **Step 4: Re-run the bootstrap test and verify it passes**

Run: `cd backend && python -m pytest test/test_bootstrap_app_factory.py::test_create_app_registers_v1_and_v2_routes -v`
Expected: PASS.

- [ ] **Step 5: Commit the bootstrap scaffold**

```bash
git add backend/app/bootstrap backend/api/v2 backend/main.py backend/config.py backend/test/test_bootstrap_app_factory.py
git commit -m "feat: add modular bootstrap and v2 router shell"
```

### Task 2: Add Platform Primitives And Worker Scaffold

**Files:**
- Create: `backend/app/platform/errors.py`
- Create: `backend/app/platform/result.py`
- Create: `backend/app/platform/events.py`
- Create: `backend/app/platform/task_queue.py`
- Create: `backend/app/platform/telemetry.py`
- Create: `backend/app/platform/sqlite.py`
- Create: `backend/worker.py`
- Create: `backend/test/test_platform_primitives.py`

- [ ] **Step 1: Write the failing platform test**

Create `backend/test/test_platform_primitives.py` with:

```python
from app.platform.result import Result
from app.platform.task_queue import InMemoryTaskQueue


def test_in_memory_task_queue_round_trips_job():
    queue = InMemoryTaskQueue()
    queue.enqueue({"job_id": "job-1", "kind": "ingest"})

    job = queue.dequeue()

    assert job["job_id"] == "job-1"
    assert Result.ok({"job_id": "job-1"}).ok is True
```

- [ ] **Step 2: Run the platform test and verify it fails**

Run: `cd backend && python -m pytest test/test_platform_primitives.py::test_in_memory_task_queue_round_trips_job -v`
Expected: FAIL because `app.platform` does not exist yet.

- [ ] **Step 3: Implement the minimal platform primitives and worker entrypoint**

Create `backend/app/platform/result.py` with:

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    ok: bool
    value: T | None = None
    error: str | None = None

    @classmethod
    def ok(cls, value: T | None = None) -> "Result[T]":
        return cls(ok=True, value=value)

    @classmethod
    def fail(cls, error: str) -> "Result[T]":
        return cls(ok=False, error=error)
```

Create `backend/app/platform/task_queue.py` with:

```python
from collections import deque


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._items = deque()

    def enqueue(self, payload: dict) -> None:
        self._items.append(payload)

    def dequeue(self) -> dict:
        return self._items.popleft()
```

Create `backend/worker.py` with:

```python
from app.bootstrap.settings import get_settings


def main() -> None:
    settings = get_settings()
    print(f"worker ready data_dir={settings.data_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Re-run the platform test**

Run: `cd backend && python -m pytest test/test_platform_primitives.py::test_in_memory_task_queue_round_trips_job -v`
Expected: PASS.

- [ ] **Step 5: Commit the platform primitives**

```bash
git add backend/app/platform backend/worker.py backend/test/test_platform_primitives.py
git commit -m "feat: add platform primitives and worker scaffold"
```

### Task 3: Introduce LightRAG Gateway And Legacy Adapters

**Files:**
- Create: `backend/test/test_lightrag_gateway_v2.py`
- Create: `backend/app/adapters/lightrag/gateway.py`
- Create: `backend/app/adapters/lightrag/schemas.py`
- Create: `backend/app/adapters/lightrag/mappers.py`
- Modify: `backend/app/infra/lightrag_client.py`
- Create: `backend/app/adapters/legacy/document_processor_adapter.py`
- Create: `backend/app/adapters/legacy/retriever_adapter.py`
- Create: `backend/app/adapters/legacy/smart_retrieval_adapter.py`

- [ ] **Step 1: Write the failing LightRAG gateway tests**

Create `backend/test/test_lightrag_gateway_v2.py` with:

```python
import pytest

from app.adapters.lightrag.gateway import LightRAGGateway
from app.adapters.lightrag.schemas import LightRAGSearchRequest


class DummyClient:
    async def query_data(self, query: str, mode: str = "hybrid", top_k: int = 10):
        return {"items": [{"doc_id": "remote-1", "text": "federated learning", "score": 0.91}]}


@pytest.mark.asyncio
async def test_gateway_maps_search_results_to_internal_dtos():
    gateway = LightRAGGateway(client=DummyClient())

    result = await gateway.search(LightRAGSearchRequest(query="federated learning", top_k=5))

    assert result.items[0].remote_document_id == "remote-1"
    assert result.items[0].score == 0.91
```

- [ ] **Step 2: Run the gateway test and verify it fails**

Run: `cd backend && python -m pytest test/test_lightrag_gateway_v2.py::test_gateway_maps_search_results_to_internal_dtos -v`
Expected: FAIL because the gateway package does not exist yet.

- [ ] **Step 3: Implement the gateway and legacy adapter package**

Create `backend/app/adapters/lightrag/schemas.py` with:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LightRAGSearchRequest:
    query: str
    mode: str = "hybrid"
    top_k: int = 10


@dataclass(frozen=True)
class LightRAGSearchItem:
    remote_document_id: str
    content: str
    score: float
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LightRAGSearchResult:
    items: list[LightRAGSearchItem]
```

Create `backend/app/adapters/lightrag/gateway.py` with:

```python
from app.adapters.lightrag.schemas import LightRAGSearchItem, LightRAGSearchRequest, LightRAGSearchResult
from app.infra.lightrag_client import LightRAGClient


class LightRAGGateway:
    def __init__(self, client: LightRAGClient | None = None):
        self.client = client or LightRAGClient()

    async def search(self, request: LightRAGSearchRequest) -> LightRAGSearchResult:
        payload = await self.client.query_data(query=request.query, mode=request.mode, top_k=request.top_k)
        items = [
            LightRAGSearchItem(
                remote_document_id=str(item.get("doc_id") or item.get("id") or ""),
                content=str(item.get("text") or item.get("content") or ""),
                score=float(item.get("score") or 0.0),
                metadata=dict(item),
            )
            for item in (payload.get("items") or payload.get("results") or [])
        ]
        return LightRAGSearchResult(items=items)
```

Create `backend/app/adapters/legacy/document_processor_adapter.py` with:

```python
from utils.document_processor import process_document


class LegacyDocumentProcessorAdapter:
    def extract(self, file_path: str):
        return process_document(file_path)
```

Create `backend/app/adapters/legacy/retriever_adapter.py` and `smart_retrieval_adapter.py` as thin wrappers over current `utils.retriever` and `utils.smart_retrieval` functions used by existing services.

- [ ] **Step 4: Re-run the LightRAG gateway test**

Run: `cd backend && python -m pytest test/test_lightrag_gateway_v2.py::test_gateway_maps_search_results_to_internal_dtos -v`
Expected: PASS.

- [ ] **Step 5: Commit the gateway and legacy adapter layer**

```bash
git add backend/app/adapters backend/test/test_lightrag_gateway_v2.py
git commit -m "feat: add lightrag gateway and legacy adapters"
```

### Task 4: Add Boundary Tests For New Architecture Rules

**Files:**
- Create: `backend/test/test_legacy_adapter_boundaries.py`

- [ ] **Step 1: Write the boundary test**

Create `backend/test/test_legacy_adapter_boundaries.py` with:

```python
from pathlib import Path


def test_modules_do_not_import_legacy_utils_directly():
    modules_dir = Path(__file__).resolve().parents[1] / "app" / "modules"
    if not modules_dir.exists():
        assert True
        return

    offenders = []
    for path in modules_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "from utils." in content or "import utils." in content:
            offenders.append(str(path))

    assert offenders == []
```

- [ ] **Step 2: Run the boundary test**

Run: `cd backend && python -m pytest test/test_legacy_adapter_boundaries.py::test_modules_do_not_import_legacy_utils_directly -v`
Expected: PASS.

- [ ] **Step 3: Commit the boundary guard**

```bash
git add backend/test/test_legacy_adapter_boundaries.py
git commit -m "test: guard modular code against direct utils imports"
```

## Verification

- [ ] Run: `cd backend && python -m pytest test/test_bootstrap_app_factory.py test/test_platform_primitives.py test/test_lightrag_gateway_v2.py test/test_legacy_adapter_boundaries.py -v`
- [ ] Run: `cd backend && python worker.py`
- [ ] Run: `cd backend && python main.py`
- [ ] Manually confirm:

```text
1. GET /health responds.
2. GET /api/v2/runtime/health responds.
3. Existing /api/v1 routes are still registered.
4. No new module code imports utils directly.
```
