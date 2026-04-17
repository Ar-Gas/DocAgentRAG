# DocAgent Rebuild Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation needed for the full rebuild by introducing settings-driven configuration, `/api/v2` scaffolding, Alembic-managed schema evolution, a centralized LLM gateway, and the first defect fixes required by the new architecture.

**Architecture:** Keep the current FastAPI application bootable while layering in the new foundation beside the legacy v1 stack. Configuration, dependency injection, migrations, and model access move to explicit modules first so later ingest, retrieval, and frontend work can depend on stable contracts instead of ad hoc globals and `utils/*` calls.

**Tech Stack:** FastAPI, Pydantic Settings, Alembic, SQLite, pytest, Doubao/OpenAI-compatible HTTP clients, Vue-compatible HTTP contracts

---

## File Structure

### Backend

- Modify: `backend/requirements.txt`
  - Add `pydantic-settings`, `alembic`, `networkx`, `reportlab`, and the BM25 dependency used by the later plans.
- Modify: `backend/config.py`
  - Replace module-level globals with a cached `Settings` object while preserving compatibility exports for the current codebase.
- Modify: `backend/main.py`
  - Register `/api/v2`, initialize the new stores and gateway, and preserve `/api/v1` during migration.
- Modify: `backend/api/document.py`
  - Restore the missing `@router.delete("/{document_id}")` decorator without changing current response semantics.
- Create: `backend/api/deps.py`
  - Centralize FastAPI dependency providers for settings, metadata store, vector store, graph store, cache, and services.
- Create: `backend/api/v2/__init__.py`
  - Aggregate the new v2 routers.
- Create: `backend/api/v2/documents.py`
  - Start the v2 document contract for upload/list/delete/detail.
- Create: `backend/api/v2/pipeline.py`
  - Expose rebuild and retry endpoints used by later plans.
- Create: `backend/api/v2/admin.py`
  - Expose health, provider status, and token usage payloads.
- Create: `backend/app/infra/cache.py`
  - Add an explicit in-memory cache abstraction for query analysis and LLM task caching.
- Create: `backend/app/infra/graph_store.py`
  - Add JSON-backed graph persistence for triples and graph payload artifacts.
- Create: `backend/app/domain/llm/gateway.py`
  - Centralized provider abstraction, retry/fallback behavior, streaming, and token tracking.
- Create: `backend/app/domain/llm/prompts.py`
  - Own the prompt templates referenced by later extraction/retrieval/QA modules.
- Create: `backend/app/schemas/document.py`
  - Define v2 document request/response models.
- Create: `backend/alembic.ini`
  - Alembic entrypoint configuration.
- Create: `backend/alembic/env.py`
  - SQLite migration environment wired to `backend/config.py`.
- Create: `backend/alembic/script.py.mako`
  - Standard Alembic revision template.
- Create: `backend/alembic/versions/20260416_0001_rebuild_foundation.py`
  - First migration for rebuild fields and new tables.
- Create: `backend/test/test_config_v2.py`
  - Lock settings loading and compatibility exports.
- Create: `backend/test/test_llm_gateway.py`
  - Lock retry, fallback, caching, and token counting behavior.
- Create: `backend/test/test_v2_admin_api.py`
  - Lock admin status and token usage responses.
- Modify: `backend/test/test_metadata_store_extensions.py`
  - Extend coverage for new metadata and graph helper methods.

### No Planned Changes In This Plan

- `backend/app/services/retrieval_service.py`
  - Retrieval logic changes belong to the retrieval plan.
- `backend/app/services/document_service.py`
  - Upload orchestration replacement belongs to the ingest plan.
- `frontend/docagent-frontend/src/*`
  - Frontend changes belong to the frontend plan.

---

### Task 1: Introduce Settings-Driven Configuration And v2 DI

**Files:**
- Create: `backend/test/test_config_v2.py`
- Modify: `backend/config.py`
- Create: `backend/api/deps.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing settings test**

Create `backend/test/test_config_v2.py` with:

```python
import importlib


def test_get_settings_reads_v2_defaults(monkeypatch):
    monkeypatch.setenv("API_VERSION", "v2")
    monkeypatch.setenv("API_PREFIX", "/api/v2")
    monkeypatch.setenv("DOUBAO_MINI_LLM_MODEL", "doubao-seed-2-0-mini-260215")

    config = importlib.import_module("config")
    importlib.reload(config)

    settings = config.get_settings()

    assert settings.api_version == "v2"
    assert settings.api_prefix == "/api/v2"
    assert settings.default_llm_model == "doubao-seed-2-0-mini-260215"
    assert config.API_PREFIX == "/api/v2"
```

- [ ] **Step 2: Run the targeted settings test and verify it fails**

Run: `cd backend && python -m pytest test/test_config_v2.py::test_get_settings_reads_v2_defaults -v`
Expected: FAIL because `get_settings()` and the new settings fields do not exist yet.

- [ ] **Step 3: Implement the settings object and dependency providers**

Refactor `backend/config.py` to:

```python
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    base_dir: Path = Path(__file__).resolve().parent
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "data")
    doc_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "doc")
    chroma_db_path: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "chromadb")
    api_version: str = "v2"
    api_prefix: str = "/api/v2"
    doubao_api_key: str = ""
    default_llm_model: str = "doubao-seed-2-0-mini-260215"
    llm_cache_ttl_seconds: int = 600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.doc_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_db_path.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
API_VERSION = settings.api_version
API_PREFIX = settings.api_prefix
DATA_DIR = settings.data_dir
DOC_DIR = settings.doc_dir
CHROMA_DB_PATH = settings.chroma_db_path
DOUBAO_API_KEY = settings.doubao_api_key
DOUBAO_DEFAULT_LLM_MODEL = settings.default_llm_model
```

Create `backend/api/deps.py` with providers like:

```python
from functools import lru_cache

from config import get_settings
from app.infra.cache import InMemoryCache
from app.infra.graph_store import GraphStore
from app.infra.metadata_store import DocumentMetadataStore
from app.infra.vector_store import VectorStore


@lru_cache(maxsize=1)
def get_metadata_store() -> DocumentMetadataStore:
    return DocumentMetadataStore(data_dir=get_settings().data_dir)


@lru_cache(maxsize=1)
def get_graph_store() -> GraphStore:
    return GraphStore(data_dir=get_settings().data_dir)


@lru_cache(maxsize=1)
def get_cache() -> InMemoryCache:
    return InMemoryCache(default_ttl=get_settings().llm_cache_ttl_seconds)
```

Update `backend/main.py` to import `get_settings()` and include the later `api.v2` router beside the existing v1 router.

- [ ] **Step 4: Re-run the targeted settings test**

Run: `cd backend && python -m pytest test/test_config_v2.py::test_get_settings_reads_v2_defaults -v`
Expected: PASS.

- [ ] **Step 5: Commit the settings and DI scaffold**

```bash
git add backend/requirements.txt \
  backend/config.py \
  backend/api/deps.py \
  backend/main.py \
  backend/test/test_config_v2.py
git commit -m "feat: add v2 settings and dependency providers"
```

### Task 2: Add Alembic Baseline And Rebuild Metadata Tables

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260416_0001_rebuild_foundation.py`
- Modify: `backend/app/infra/metadata_store.py`
- Create: `backend/app/infra/graph_store.py`
- Modify: `backend/test/test_metadata_store_extensions.py`

- [ ] **Step 1: Write the failing metadata and graph persistence tests**

Append to `backend/test/test_metadata_store_extensions.py`:

```python
from pathlib import Path

from app.infra.graph_store import GraphStore
from app.infra.metadata_store import DocumentMetadataStore


def test_metadata_store_persists_llm_fields_and_entities(tmp_path: Path):
    store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)
    store.upsert_document(
        {
            "id": "doc-1",
            "filename": "report.pdf",
            "filepath": "/tmp/report.pdf",
            "file_type": ".pdf",
            "llm_doc_type": "报告",
            "llm_summary": "三句摘要",
            "llm_detailed_summary": "详细摘要",
            "duplicate_of": None,
            "related_docs": ["doc-2"],
            "ingest_status": "ready",
        }
    )
    store.save_entities(
        "doc-1",
        [{"entity_text": "联邦学习", "entity_type": "CONCEPT", "context": "联邦学习用于隐私保护"}],
    )

    document = store.get_document("doc-1")
    entities = store.list_entities("doc-1")

    assert document["llm_doc_type"] == "报告"
    assert entities[0]["entity_text"] == "联邦学习"


def test_graph_store_round_trips_doc_triples(tmp_path: Path):
    store = GraphStore(data_dir=tmp_path)
    store.save_triples(
        "doc-1",
        [{"subject": "联邦学习", "predicate": "提升", "object": "隐私保护", "confidence": 0.91}],
    )

    triples = store.get_triples(["doc-1"])

    assert triples[0]["subject"] == "联邦学习"
    assert triples[0]["confidence"] == 0.91
```

- [ ] **Step 2: Run the metadata-store extension test and verify it fails**

Run: `cd backend && python -m pytest test/test_metadata_store_extensions.py -v`
Expected: FAIL because the new document fields, entity methods, and `GraphStore` do not exist yet.

- [ ] **Step 3: Implement the migration and persistence layer**

Create `backend/alembic/versions/20260416_0001_rebuild_foundation.py` with:

```python
from alembic import op
import sqlalchemy as sa


revision = "20260416_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("llm_doc_type", sa.Text(), nullable=True))
        batch.add_column(sa.Column("llm_summary", sa.Text(), nullable=True))
        batch.add_column(sa.Column("llm_detailed_summary", sa.Text(), nullable=True))
        batch.add_column(sa.Column("duplicate_of", sa.Text(), nullable=True))
        batch.add_column(sa.Column("related_docs", sa.Text(), nullable=True))
        batch.add_column(sa.Column("ingest_status", sa.Text(), nullable=False, server_default="pending"))

    op.create_table(
        "doc_entities",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("entity_text", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_doc_entities_text", "doc_entities", ["entity_text"])
    op.create_index("idx_doc_entities_doc", "doc_entities", ["doc_id"])

    op.create_table(
        "qa_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("doc_ids", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "kg_triples",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("predicate", sa.Text(), nullable=False),
        sa.Column("object", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.create_index("idx_kg_subject", "kg_triples", ["subject"])
    op.create_index("idx_kg_object", "kg_triples", ["object"])

    op.create_table(
        "classification_feedback",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("original_label", sa.Text(), nullable=True),
        sa.Column("corrected_label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
```

Extend `backend/app/infra/metadata_store.py` with:

```python
def save_entities(self, document_id: str, entities: list[dict]) -> None:
    with self._connect() as connection:
        connection.execute("DELETE FROM doc_entities WHERE doc_id = ?", (document_id,))
        connection.executemany(
            """
            INSERT INTO doc_entities (id, doc_id, entity_text, entity_type, context)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (str(uuid.uuid4()), document_id, item["entity_text"], item["entity_type"], item.get("context"))
                for item in entities
            ],
        )
        connection.commit()

def list_entities(self, document_id: str) -> list[dict]:
    with self._connect() as connection:
        rows = connection.execute(
            "SELECT id, doc_id, entity_text, entity_type, context, created_at FROM doc_entities WHERE doc_id = ? ORDER BY created_at ASC",
            (document_id,),
        ).fetchall()
    return [dict(row) for row in rows]
```

Create `backend/app/infra/graph_store.py` with:

```python
import json
import uuid
from pathlib import Path

from app.core.database import connect_sqlite
from config import get_settings


class GraphStore:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir or get_settings().data_dir)
        self.db_path = self.data_dir / "docagent.db"
        self.graph_dir = self.data_dir / "graphs"
        self.graph_dir.mkdir(parents=True, exist_ok=True)

    def save_triples(self, doc_id: str, triples: list[dict]) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.execute("DELETE FROM kg_triples WHERE doc_id = ?", (doc_id,))
            connection.executemany(
                """
                INSERT INTO kg_triples (id, doc_id, subject, predicate, object, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (str(uuid.uuid4()), doc_id, item["subject"], item["predicate"], item["object"], item.get("confidence", 1.0))
                    for item in triples
                ],
            )
            connection.commit()
        (self.graph_dir / f"{doc_id}.json").write_text(json.dumps(triples, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_triples(self, doc_ids: list[str]) -> list[dict]:
        if not doc_ids:
            return []
        placeholders = ",".join("?" for _ in doc_ids)
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(
                f"SELECT id, doc_id, subject, predicate, object, confidence FROM kg_triples WHERE doc_id IN ({placeholders})",
                tuple(doc_ids),
            ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Re-run the metadata-store extension test**

Run: `cd backend && python -m pytest test/test_metadata_store_extensions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the migration and persistence layer**

```bash
git add backend/alembic.ini \
  backend/alembic/env.py \
  backend/alembic/script.py.mako \
  backend/alembic/versions/20260416_0001_rebuild_foundation.py \
  backend/app/infra/metadata_store.py \
  backend/app/infra/graph_store.py \
  backend/test/test_metadata_store_extensions.py
git commit -m "feat: add rebuild schema migration and graph persistence"
```

### Task 3: Build LLM Gateway, v2 Admin Routes, And Fix Document Delete

**Files:**
- Create: `backend/test/test_llm_gateway.py`
- Create: `backend/test/test_v2_admin_api.py`
- Create: `backend/app/domain/llm/gateway.py`
- Create: `backend/app/domain/llm/prompts.py`
- Create: `backend/api/v2/__init__.py`
- Create: `backend/api/v2/documents.py`
- Create: `backend/api/v2/pipeline.py`
- Create: `backend/api/v2/admin.py`
- Modify: `backend/api/document.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing gateway and admin tests**

Create `backend/test/test_llm_gateway.py`:

```python
import pytest

from app.domain.llm.gateway import LLMGateway


@pytest.mark.asyncio
async def test_llm_gateway_falls_back_and_records_usage():
    calls = []

    async def fake_provider(model: str, prompt: str, stream: bool = False):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("primary failed")
        return {"content": '{"intent":"事实查找"}', "tokens_used": 17, "model": model}

    gateway = LLMGateway(
        providers={"primary": fake_provider, "fallback": fake_provider},
        task_models={"query_analyze": ["primary", "fallback"]},
    )

    response = await gateway.call('test prompt', task='query_analyze', use_cache=False)

    assert response.content == '{"intent":"事实查找"}'
    assert response.tokens_used == 17
    assert calls == ["primary", "fallback"]
```

Create `backend/test/test_v2_admin_api.py`:

```python
from fastapi.testclient import TestClient

from main import app


def test_v2_admin_status_returns_provider_and_tokens(monkeypatch):
    from api.v2 import admin as admin_api

    monkeypatch.setattr(
        admin_api,
        "get_admin_status_payload",
        lambda: {
            "llm": {"provider": "doubao", "default_model": "doubao-seed-2-0-mini-260215"},
            "token_usage": {"query_analyze": 42},
        },
    )

    client = TestClient(app)
    response = client.get("/api/v2/admin/status")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["llm"]["provider"] == "doubao"
    assert payload["token_usage"]["query_analyze"] == 42
```

- [ ] **Step 2: Run the targeted gateway/admin tests and verify they fail**

Run: `cd backend && python -m pytest test/test_llm_gateway.py test/test_v2_admin_api.py -v`
Expected: FAIL because the gateway and `/api/v2/admin/status` route do not exist yet.

- [ ] **Step 3: Implement the gateway, new routers, and delete fix**

Create `backend/app/domain/llm/gateway.py` with:

```python
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class LLMResponse:
    content: str
    tokens_used: int
    model: str


class LLMGateway:
    def __init__(self, providers: dict, task_models: dict, cache=None):
        self.providers = providers
        self.task_models = task_models
        self.cache = cache
        self.token_usage = defaultdict(int)

    async def call(self, prompt: str, task: str, use_cache: bool = True) -> LLMResponse:
        cache_key = f"{task}:{prompt}"
        if use_cache and self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        errors = []
        for model in self.task_models.get(task, []):
            provider = self.providers[model]
            try:
                raw = await provider(model=model, prompt=prompt, stream=False)
                response = LLMResponse(
                    content=raw["content"],
                    tokens_used=raw.get("tokens_used", 0),
                    model=raw.get("model", model),
                )
                self.token_usage[task] += response.tokens_used
                if use_cache and self.cache:
                    self.cache.set(cache_key, response)
                return response
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        raise RuntimeError("; ".join(errors))
```

Create `backend/api/v2/admin.py`:

```python
from fastapi import APIRouter

from api import success

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_status_payload() -> dict:
    from api.deps import get_llm_gateway

    gateway = get_llm_gateway()
    return {
        "llm": {
            "provider": "doubao",
            "default_model": gateway.task_models.get("query_analyze", ["unknown"])[0],
        },
        "token_usage": dict(gateway.token_usage),
    }


@router.get("/status", summary="获取系统状态与 token 用量")
async def get_admin_status():
    return success(data=get_admin_status_payload())
```

Create `backend/api/v2/documents.py`:

```python
from fastapi import APIRouter, Depends, Query, UploadFile, File

from api import paginated, success
from api.deps import get_document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", summary="上传文档")
async def upload_document(file: UploadFile = File(...), service=Depends(get_document_service)):
    payload = await service.upload_v2(file)
    return success(data=payload, message="文档上传成功")


@router.get("", summary="获取文档列表")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    service=Depends(get_document_service),
):
    payload = await service.list_documents_v2(page=page, page_size=page_size)
    return paginated(items=payload["items"], total=payload["total"], page=page, page_size=page_size)


@router.delete("/{document_id}", summary="删除文档")
async def delete_document(document_id: str, service=Depends(get_document_service)):
    result = await service.delete_v2(document_id)
    return success(data=result, message="文档删除成功")
```

Create `backend/api/v2/pipeline.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api import success
from api.deps import get_pipeline_service

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class RetryRequest(BaseModel):
    document_id: str


class BatchDocumentsRequest(BaseModel):
    doc_ids: list[str]


@router.post("/rebuild-indexes", summary="重建索引")
async def rebuild_indexes(service=Depends(get_pipeline_service)):
    payload = await service.rebuild_indexes()
    return success(data=payload, message="索引重建任务已启动")


@router.post("/retry", summary="重试失败入库")
async def retry_pipeline(request: RetryRequest, service=Depends(get_pipeline_service)):
    payload = await service.retry_document(request.document_id)
    return success(data=payload, message="入库重试任务已启动")


@router.post("/rerun-summary", summary="批量重跑摘要")
async def rerun_summary(request: BatchDocumentsRequest, service=Depends(get_pipeline_service)):
    payload = await service.rerun_summary(request.doc_ids)
    return success(data=payload, message="摘要任务已启动")


@router.post("/rerun-classification", summary="批量重跑分类")
async def rerun_classification(request: BatchDocumentsRequest, service=Depends(get_pipeline_service)):
    payload = await service.rerun_classification(request.doc_ids)
    return success(data=payload, message="分类任务已启动")
```

Fix `backend/api/document.py` by changing:

```python
async def delete_document_api(document_id: str):
```

to:

```python
@router.delete("/{document_id}", summary="删除文档")
async def delete_document_api(document_id: str):
```

Update `backend/main.py` to:

```python
from api.v2 import router as api_v2_router

app.include_router(api_router, prefix="/api/v1")
app.include_router(api_v2_router, prefix="/api/v2")
```

- [ ] **Step 4: Re-run the targeted gateway/admin tests**

Run: `cd backend && python -m pytest test/test_llm_gateway.py test/test_v2_admin_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the gateway, v2 routers, and delete fix**

```bash
git add backend/app/domain/llm/gateway.py \
  backend/app/domain/llm/prompts.py \
  backend/api/v2/__init__.py \
  backend/api/v2/documents.py \
  backend/api/v2/pipeline.py \
  backend/api/v2/admin.py \
  backend/api/document.py \
  backend/main.py \
  backend/test/test_llm_gateway.py \
  backend/test/test_v2_admin_api.py
git commit -m "feat: add llm gateway and v2 foundation routes"
```

### Task 4: Verify The Foundation Layer End To End

**Files:**
- Verify only; no new files

- [ ] **Step 1: Run the focused backend foundation test set**

Run:

```bash
cd backend && python -m pytest \
  test/test_config_v2.py \
  test/test_metadata_store_extensions.py \
  test/test_llm_gateway.py \
  test/test_v2_admin_api.py \
  -v
```

Expected: PASS for all targeted rebuild-foundation tests.

- [ ] **Step 2: Run the existing document API regression for delete wiring**

Run: `cd backend && python -m pytest test/test_document_reader_api.py test/test_retrieval_service_api.py -v`
Expected: PASS or only fail on known pre-existing unrelated assertions. If a failure is caused by the `/documents/{id}` delete decorator change or `/api/v2` wiring, fix it before proceeding.

- [ ] **Step 3: Smoke-test the migration command**

Run:

```bash
cd backend && alembic upgrade head
```

Expected: the SQLite database upgrades successfully with the new tables present.

- [ ] **Step 4: Record the verified commands in the PR or work log**

Copy these exact commands into the implementation notes:

```text
cd backend && python -m pytest test/test_config_v2.py test/test_metadata_store_extensions.py test/test_llm_gateway.py test/test_v2_admin_api.py -v
cd backend && alembic upgrade head
```

- [ ] **Step 5: Commit any verification-only fixes**

```bash
git add backend
git commit -m "test: verify rebuild foundation layer"
```
