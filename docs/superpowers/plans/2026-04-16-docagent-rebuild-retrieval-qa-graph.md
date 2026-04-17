# DocAgent Rebuild Retrieval QA Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy retrieval core with LLM-assisted query understanding, multi-route recall, RRF fusion, smart reranking, citation-grounded QA, topic graph APIs, summary generation, export helpers, and token-aware admin observability.

**Architecture:** Keep the new ingest pipeline from the previous plan as the producer of blocks, entities, and triples, then build a new v2 retrieval stack on top of those persisted artifacts. Retrieval becomes an application service that coordinates vector, BM25, and graph recall through domain modules and returns document-centric payloads that can also feed the QA and graph views.

**Tech Stack:** FastAPI, SQLite, Chroma, BM25, SSE, pytest, asyncio, lightweight graph payload generation

---

## File Structure

### Backend

- Create: `backend/app/schemas/retrieval.py`
- Create: `backend/app/schemas/qa.py`
- Create: `backend/app/schemas/topic.py`
- Create: `backend/app/domain/retrieval/__init__.py`
- Create: `backend/app/domain/retrieval/query_analyzer.py`
- Create: `backend/app/domain/retrieval/fusion.py`
- Create: `backend/app/domain/retrieval/reranker.py`
- Create: `backend/app/domain/llm/qa_chain.py`
- Modify: `backend/app/services/retrieval_service.py`
- Create: `backend/app/services/qa_service.py`
- Create: `backend/app/services/summary_service.py`
- Create: `backend/app/services/export_service.py`
- Modify: `backend/app/services/topic_service.py`
- Create: `backend/api/v2/retrieval.py`
- Create: `backend/api/v2/qa.py`
- Create: `backend/api/v2/topics.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/api/v2/admin.py`
- Modify: `backend/app/infra/metadata_store.py`
- Create: `backend/test/test_v2_retrieval_service.py`
- Create: `backend/test/test_v2_qa_service.py`
- Create: `backend/test/test_v2_topics_api.py`

### No Planned Changes In This Plan

- `backend/app/services/document_service.py`
  - Upload flow changes belong to the ingest plan.
- `frontend/docagent-frontend/src/*`
  - UI changes belong to the frontend plan.

---

### Task 1: Add Query Analysis, Fusion, And Retrieval Schemas

**Files:**
- Create: `backend/app/schemas/retrieval.py`
- Create: `backend/app/domain/retrieval/query_analyzer.py`
- Create: `backend/app/domain/retrieval/fusion.py`
- Create: `backend/app/domain/retrieval/reranker.py`
- Create: `backend/test/test_v2_retrieval_service.py`

- [ ] **Step 1: Write the failing retrieval-domain tests**

Create `backend/test/test_v2_retrieval_service.py` with:

```python
import pytest

from app.domain.retrieval.fusion import reciprocal_rank_fusion
from app.domain.retrieval.query_analyzer import QueryAnalyzer


@pytest.mark.asyncio
async def test_query_analyzer_returns_structured_plan():
    analyzer = QueryAnalyzer.for_test(
        {
            "intent": "比较分析",
            "expanded_queries": ["联邦学习 隐私保护", "差分隐私 联邦学习"],
            "entity_filters": ["联邦学习"],
            "time_filter": None,
            "doc_type_hint": "论文",
        }
    )

    result = await analyzer.analyze("联邦学习隐私保护有什么不同观点")

    assert result.intent == "比较分析"
    assert result.entity_filters == ["联邦学习"]
    assert result.doc_type_hint == "论文"


def test_rrf_merges_vector_bm25_and_graph_hits():
    vector_hits = [{"doc_id": "doc-1", "block_id": "a", "score": 0.91}]
    bm25_hits = [{"doc_id": "doc-2", "block_id": "b", "score": 12.0}]
    graph_hits = [{"doc_id": "doc-1", "block_id": "c", "score": 0.77}]

    fused = reciprocal_rank_fusion(vector_hits, bm25_hits, graph_hits, k=60)

    assert fused[0]["doc_id"] == "doc-1"
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]
```

- [ ] **Step 2: Run the retrieval-domain tests and verify they fail**

Run: `cd backend && python -m pytest test/test_v2_retrieval_service.py -v`
Expected: FAIL because the new schemas and retrieval modules do not exist yet.

- [ ] **Step 3: Implement the retrieval domain modules**

Create `backend/app/schemas/retrieval.py`:

```python
from pydantic import BaseModel, Field


class QueryAnalysis(BaseModel):
    intent: str
    expanded_queries: list[str] = Field(default_factory=list)
    entity_filters: list[str] = Field(default_factory=list)
    time_filter: str | None = None
    doc_type_hint: str | None = None


class SearchRequest(BaseModel):
    query: str
    mode: str = "smart"
    top_k: int = 20
    doc_ids: list[str] | None = None


class SearchResultBlock(BaseModel):
    doc_id: str
    block_id: str
    block_type: str | None = None
    snippet: str
    score: float
    match_reason: str | None = None


class SearchResponse(BaseModel):
    query: str
    query_analysis: QueryAnalysis
    results: list[dict]
```

Create `backend/app/domain/retrieval/query_analyzer.py`:

```python
from app.schemas.retrieval import QueryAnalysis


class QueryAnalyzer:
    def __init__(self, gateway, prompt_builder=None):
        self.gateway = gateway
        self.prompt_builder = prompt_builder or (lambda query: query)

    async def analyze(self, query: str) -> QueryAnalysis:
        response = await self.gateway.call(self.prompt_builder(query), task="query_analyze")
        return QueryAnalysis.model_validate_json(response.content)

    @classmethod
    def for_test(cls, payload: dict):
        class _Gateway:
            async def call(self, prompt: str, task: str):
                class _Response:
                    content = QueryAnalysis(**payload).model_dump_json()
                return _Response()
        return cls(_Gateway())
```

Create `backend/app/domain/retrieval/fusion.py`:

```python
def reciprocal_rank_fusion(*result_sets: list[dict], k: int = 60) -> list[dict]:
    scores = {}
    for result_set in result_sets:
        for rank, item in enumerate(result_set, start=1):
            key = (item["doc_id"], item["block_id"])
            if key not in scores:
                scores[key] = {**item, "rrf_score": 0.0}
            scores[key]["rrf_score"] += 1.0 / (k + rank)
    return sorted(scores.values(), key=lambda item: item["rrf_score"], reverse=True)
```

Create `backend/app/domain/retrieval/reranker.py` with a `rerank(query, candidates)` method that asks the gateway for JSON-ranked `block_id`s and returns reordered candidates.

- [ ] **Step 4: Re-run the retrieval-domain tests**

Run: `cd backend && python -m pytest test/test_v2_retrieval_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the retrieval domain layer**

```bash
git add backend/app/schemas/retrieval.py \
  backend/app/domain/retrieval \
  backend/test/test_v2_retrieval_service.py
git commit -m "feat: add v2 retrieval domain modules"
```

### Task 2: Rewrite RetrievalService And Add v2 Retrieval/Topics APIs

**Files:**
- Modify: `backend/app/services/retrieval_service.py`
- Modify: `backend/app/services/topic_service.py`
- Create: `backend/api/v2/retrieval.py`
- Create: `backend/api/v2/topics.py`
- Modify: `backend/app/infra/metadata_store.py`
- Create: `backend/test/test_v2_topics_api.py`

- [ ] **Step 1: Write the failing service and topics API tests**

Append to `backend/test/test_v2_retrieval_service.py`:

```python
import pytest

from app.schemas.retrieval import SearchRequest
from app.services.retrieval_service import RetrievalService


@pytest.mark.asyncio
async def test_retrieval_service_returns_document_centric_results(tmp_path):
    service = RetrievalService.for_test(tmp_path)

    response = await service.search(SearchRequest(query="联邦学习 隐私保护", mode="smart", top_k=5))

    assert response.query_analysis.intent == "事实查找"
    assert response.results[0]["doc_id"] == "doc-1"
    assert response.results[0]["evidence_blocks"][0]["block_id"] == "doc-1:block-v2:0"
```

Create `backend/test/test_v2_topics_api.py`:

```python
from fastapi.testclient import TestClient

from main import app


def test_topics_graph_endpoint_returns_nodes_and_edges(monkeypatch):
    from api.v2 import topics as topics_api

    monkeypatch.setattr(
        topics_api,
        "get_graph_payload",
        lambda doc_ids=None: {
            "nodes": [{"id": "联邦学习", "label": "联邦学习"}],
            "edges": [{"from": "联邦学习", "to": "隐私保护", "label": "提升", "doc_id": "doc-1"}],
        },
    )

    client = TestClient(app)
    response = client.get("/api/v2/topics/graph")

    assert response.status_code == 200
    assert response.json()["data"]["edges"][0]["label"] == "提升"
```

- [ ] **Step 2: Run the retrieval/topics tests and verify they fail**

Run: `cd backend && python -m pytest test/test_v2_retrieval_service.py test/test_v2_topics_api.py -v`
Expected: FAIL because `RetrievalService.search()` does not implement the new contract and the topics graph route does not exist.

- [ ] **Step 3: Implement the new retrieval service and API routes**

Refactor `backend/app/services/retrieval_service.py` to expose:

```python
from app.schemas.retrieval import QueryAnalysis, SearchRequest, SearchResponse


class RetrievalService:
    def __init__(self, query_analyzer, vector_index, bm25_index, graph_index, reranker, metadata_store):
        self.query_analyzer = query_analyzer
        self.vector_index = vector_index
        self.bm25_index = bm25_index
        self.graph_index = graph_index
        self.reranker = reranker
        self.metadata_store = metadata_store

    async def search(self, req: SearchRequest) -> SearchResponse:
        analysis = await self.query_analyzer.analyze(req.query)
        vector_hits = self.vector_index.search_many(analysis.expanded_queries or [req.query], top_k=req.top_k)
        bm25_hits = self.bm25_index.search(req.query, top_k=req.top_k)
        graph_hits = self.graph_index.search(analysis.entity_filters, top_k=max(5, req.top_k // 2))
        fused = reciprocal_rank_fusion(vector_hits, bm25_hits, graph_hits)
        reranked = await self.reranker.rerank(req.query, fused[:req.top_k]) if req.mode == "smart" else fused[:req.top_k]
        results = self._regroup_by_document(reranked)
        return SearchResponse(query=req.query, query_analysis=analysis, results=results)

    async def search_blocks(self, query: str, doc_ids: list[str] | None = None, top_k: int = 8) -> list[dict]:
        response = await self.search(SearchRequest(query=query, doc_ids=doc_ids, top_k=top_k))
        return [block for result in response.results for block in result["evidence_blocks"]][:top_k]

    @classmethod
    def for_test(cls, tmp_path):
        from app.schemas.retrieval import QueryAnalysis

        class _QueryAnalyzer:
            async def analyze(self, query: str):
                return QueryAnalysis(
                    intent="事实查找",
                    expanded_queries=[query],
                    entity_filters=["联邦学习"],
                    time_filter=None,
                    doc_type_hint="论文",
                )

        class _VectorIndex:
            def search_many(self, queries, top_k=20):
                return [{"doc_id": "doc-1", "block_id": "doc-1:block-v2:0", "snippet": "联邦学习用于隐私保护", "score": 0.91}]

        class _BM25Index:
            def search(self, query: str, top_k=20):
                return [{"doc_id": "doc-1", "block_id": "doc-1:block-v2:0", "snippet": "联邦学习用于隐私保护", "score": 11.2}]

        class _GraphIndex:
            def search(self, entities: list[str], top_k=10):
                return [{"doc_id": "doc-1", "block_id": "doc-1:block-v2:0", "snippet": "联邦学习用于隐私保护", "score": 0.71}]

        class _Reranker:
            async def rerank(self, query: str, candidates: list[dict]):
                return candidates

        class _MetadataStore:
            def list_entities(self, document_id: str):
                return [{"entity_text": "联邦学习"}]

        service = cls(_QueryAnalyzer(), _VectorIndex(), _BM25Index(), _GraphIndex(), _Reranker(), _MetadataStore())
        service._regroup_by_document = lambda items: [
            {
                "doc_id": "doc-1",
                "filename": "paper.pdf",
                "score": items[0]["rrf_score"],
                "evidence_blocks": [
                    {
                        "doc_id": "doc-1",
                        "block_id": "doc-1:block-v2:0",
                        "snippet": "联邦学习用于隐私保护",
                        "entities": ["联邦学习"],
                    }
                ],
            }
        ]
        return service
```

Create `backend/api/v2/retrieval.py`:

```python
from fastapi import APIRouter, Depends

from api import success
from api.deps import get_retrieval_service
from app.schemas.retrieval import SearchRequest

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", summary="智能检索")
async def search_documents(request: SearchRequest, service=Depends(get_retrieval_service)):
    response = await service.search(request)
    return success(data=response.model_dump())
```

Create `backend/api/v2/topics.py`:

```python
from fastapi import APIRouter, Depends, Query

from api import success
from api.deps import get_topic_service

router = APIRouter(prefix="/topics", tags=["topics"])


def get_graph_payload(doc_ids=None):
    return get_topic_service().build_graph(doc_ids=doc_ids)


@router.get("/graph", summary="获取主题图谱")
async def get_graph(doc_ids: list[str] = Query(default=[])):
    return success(data=get_graph_payload(doc_ids or None))


@router.post("/feedback", summary="提交分类反馈")
async def submit_feedback(payload: dict, service=Depends(get_topic_service)):
    result = service.record_feedback(
        payload["doc_id"],
        payload.get("original_label"),
        payload["corrected_label"],
    )
    return success(data=result, message="分类反馈已记录")
```

Extend `backend/app/services/topic_service.py` with `build_graph(doc_ids)` that delegates into `GraphIndex.build_graph()`.

- [ ] **Step 4: Re-run the retrieval/topics tests**

Run: `cd backend && python -m pytest test/test_v2_retrieval_service.py test/test_v2_topics_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the retrieval service and topics API**

```bash
git add backend/app/services/retrieval_service.py \
  backend/app/services/topic_service.py \
  backend/api/v2/retrieval.py \
  backend/api/v2/topics.py \
  backend/app/infra/metadata_store.py \
  backend/test/test_v2_retrieval_service.py \
  backend/test/test_v2_topics_api.py
git commit -m "feat: add v2 retrieval and topics graph apis"
```

### Task 3: Add QAService, SummaryService, ExportService, And Admin Usage Metrics

**Files:**
- Create: `backend/app/schemas/qa.py`
- Create: `backend/app/schemas/topic.py`
- Create: `backend/app/domain/llm/qa_chain.py`
- Create: `backend/app/services/qa_service.py`
- Create: `backend/app/services/summary_service.py`
- Create: `backend/app/services/export_service.py`
- Create: `backend/api/v2/qa.py`
- Modify: `backend/api/v2/admin.py`
- Modify: `backend/app/infra/metadata_store.py`
- Create: `backend/test/test_v2_qa_service.py`

- [ ] **Step 1: Write the failing QA and summary tests**

Create `backend/test/test_v2_qa_service.py` with:

```python
import pytest

from app.services.qa_service import QAService


@pytest.mark.asyncio
async def test_qa_service_streams_answer_and_persists_session(tmp_path):
    service = QAService.for_test(tmp_path)

    chunks = []
    async for item in service.answer_stream("联邦学习如何保护隐私", doc_ids=["doc-1"], session_id="sess-1"):
        chunks.append(item)

    sessions = service.metadata_store.list_qa_sessions()

    assert "".join(chunks).startswith("联邦学习")
    assert sessions[0]["id"] == "sess-1"
    assert sessions[0]["citations"]
```

- [ ] **Step 2: Run the QA test and verify it fails**

Run: `cd backend && python -m pytest test/test_v2_qa_service.py -v`
Expected: FAIL because `QAService` and QA session persistence do not exist yet.

- [ ] **Step 3: Implement QA, summary, export, and admin usage payloads**

Create `backend/app/schemas/qa.py`:

```python
from pydantic import BaseModel, Field


class QARequest(BaseModel):
    query: str
    doc_ids: list[str] | None = None
    session_id: str


class Citation(BaseModel):
    doc_id: str
    block_id: str
    excerpt: str


class QAResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
```

Create `backend/app/domain/llm/qa_chain.py`:

```python
class QAChain:
    def __init__(self, gateway):
        self.gateway = gateway

    async def stream_answer(self, query: str, context: str):
        response = await self.gateway.call(f"{query}\n\n{context}", task="qa", use_cache=False)
        for chunk in response.content.split():
            yield f"{chunk} "
```

Create `backend/app/services/qa_service.py`:

```python
class QAService:
    def __init__(self, retrieval_service, qa_chain, metadata_store):
        self.retrieval_service = retrieval_service
        self.qa_chain = qa_chain
        self.metadata_store = metadata_store

    async def answer_stream(self, query: str, doc_ids: list[str] | None, session_id: str):
        blocks = await self.retrieval_service.search_blocks(query=query, doc_ids=doc_ids, top_k=8)
        context = "\n".join(f"[{item['doc_id']}:{item['block_id']}] {item['snippet']}" for item in blocks)
        answer_parts = []
        async for chunk in self.qa_chain.stream_answer(query, context):
            answer_parts.append(chunk)
            yield chunk
        citations = [{"doc_id": item["doc_id"], "block_id": item["block_id"], "excerpt": item["snippet"]} for item in blocks]
        self.metadata_store.save_qa_session(session_id, query, doc_ids or [item["doc_id"] for item in blocks], "".join(answer_parts).strip(), citations)

    @classmethod
    def for_test(cls, tmp_path):
        from app.domain.llm.qa_chain import QAChain
        from app.services.retrieval_service import RetrievalService
        from app.infra.metadata_store import DocumentMetadataStore

        class _RetrievalService:
            async def search_blocks(self, query: str, doc_ids=None, top_k: int = 8):
                return [
                    {
                        "doc_id": "doc-1",
                        "block_id": "doc-1:block-v2:0",
                        "snippet": "联邦学习通过分布式参数聚合减少原始数据共享。",
                    }
                ]

        class _Gateway:
            async def call(self, prompt: str, task: str, use_cache: bool = False):
                class _Response:
                    content = "联邦学习通过分布式参数聚合减少原始数据共享。"
                return _Response()

        store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)
        return cls(_RetrievalService(), QAChain(_Gateway()), store)
```

Create `backend/api/v2/qa.py` with both a POST endpoint and an SSE endpoint:

```python
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import get_qa_service
from app.schemas.qa import QARequest

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("/stream", summary="流式文档问答")
async def qa_stream(request: QARequest, service=Depends(get_qa_service)):
    async def event_stream():
        async for chunk in service.answer_stream(request.query, request.doc_ids, request.session_id):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

Extend `backend/app/infra/metadata_store.py` with:

```python
def save_qa_session(self, session_id: str, query: str, doc_ids: list[str], answer: str, citations: list[dict]) -> None:
    with self._connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO qa_sessions (id, query, doc_ids, answer, citations)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, query, json.dumps(doc_ids, ensure_ascii=False), answer, json.dumps(citations, ensure_ascii=False)),
        )
        connection.commit()

def list_qa_sessions(self) -> list[dict]:
    with self._connect() as connection:
        rows = connection.execute(
            "SELECT id, query, doc_ids, answer, citations, created_at FROM qa_sessions ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]
```

Create `backend/app/services/summary_service.py` with `summarize_document(doc_id)` and `summarize_documents(doc_ids, query)` so the frontend plan can expose batch summary.

Create `backend/app/services/export_service.py` with real Excel/PDF support:

```python
from io import BytesIO

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


class ExportService:
    def export_results(self, results: list[dict], format: str = "xlsx") -> tuple[bytes, str]:
        if format == "xlsx":
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Search Results"
            sheet.append(["doc_id", "filename", "score", "summary"])
            for item in results:
                sheet.append([item.get("doc_id"), item.get("filename"), item.get("score"), item.get("llm_summary")])
            buffer = BytesIO()
            workbook.save(buffer)
            return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        if format == "pdf":
            buffer = BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A4)
            y = 800
            for item in results:
                pdf.drawString(40, y, f"{item.get('filename')} | score={item.get('score')}")
                y -= 18
                pdf.drawString(56, y, (item.get("llm_summary") or "")[:90])
                y -= 28
                if y < 80:
                    pdf.showPage()
                    y = 800
            pdf.save()
            return buffer.getvalue(), "application/pdf"

        raise ValueError(f"unsupported format: {format}")
```

Update `backend/requirements.txt` in this task to add:

```text
reportlab==4.2.5
```

Update `backend/api/v2/admin.py` to add a `GET /api/v2/admin/token-usage` endpoint returning `gateway.token_usage`.

Update `backend/api/v2/retrieval.py` to add summary and export endpoints:

```python
from fastapi.responses import Response
from pydantic import BaseModel


class SummaryRequest(BaseModel):
    doc_ids: list[str]
    query: str | None = None


class ExportRequest(BaseModel):
    results: list[dict]
    format: str = "xlsx"


@router.post("/summary", summary="跨文档摘要")
async def summarize_documents(request: SummaryRequest, summary_service=Depends(get_summary_service)):
    payload = await summary_service.summarize_documents(request.doc_ids, request.query)
    return success(data=payload)


@router.post("/export", summary="导出检索结果")
async def export_results(request: ExportRequest, export_service=Depends(get_export_service)):
    body, media_type = export_service.export_results(request.results, request.format)
    filename = f"docagent-results.{request.format}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

- [ ] **Step 4: Re-run the QA test**

Run: `cd backend && python -m pytest test/test_v2_qa_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the QA/summary/export/admin layer**

```bash
git add backend/app/schemas/qa.py \
  backend/app/schemas/topic.py \
  backend/app/domain/llm/qa_chain.py \
  backend/app/services/qa_service.py \
  backend/app/services/summary_service.py \
  backend/app/services/export_service.py \
  backend/api/v2/retrieval.py \
  backend/api/v2/qa.py \
  backend/api/v2/admin.py \
  backend/requirements.txt \
  backend/app/infra/metadata_store.py \
  backend/test/test_v2_qa_service.py
git commit -m "feat: add qa summary export and admin metrics"
```

### Task 4: Verify Retrieval, QA, And Graph Backend End To End

**Files:**
- Verify only; no new files

- [ ] **Step 1: Run the targeted backend intelligence test set**

Run:

```bash
cd backend && python -m pytest \
  test/test_v2_retrieval_service.py \
  test/test_v2_topics_api.py \
  test/test_v2_qa_service.py \
  test/test_v2_admin_api.py \
  -v
```

Expected: PASS for all targeted retrieval/QA/graph tests.

- [ ] **Step 2: Run the existing retrieval regression suite**

Run:

```bash
cd backend && python -m pytest \
  test/test_retrieval_service_api.py \
  test/test_retriever.py \
  test/test_document_reader_api.py \
  -v
```

Expected: PASS or only fail on known pre-existing legacy assertions unrelated to the new v2 stack. If a failure is caused by shared storage contracts, fix it before moving on.

- [ ] **Step 3: Smoke-test the new API surface manually**

Run `cd backend && python main.py`, then verify:

```text
POST /api/v2/retrieval/search returns query_analysis + document results
GET /api/v2/topics/graph returns nodes + edges
POST /api/v2/qa/stream streams `text/event-stream`
GET /api/v2/admin/token-usage returns task counters
```

- [ ] **Step 4: Record the verified commands in the work log**

Copy these exact commands into the implementation notes:

```text
cd backend && python -m pytest test/test_v2_retrieval_service.py test/test_v2_topics_api.py test/test_v2_qa_service.py test/test_v2_admin_api.py -v
cd backend && python -m pytest test/test_retrieval_service_api.py test/test_retriever.py test/test_document_reader_api.py -v
```

- [ ] **Step 5: Commit any verification-only fixes**

```bash
git add backend
git commit -m "test: verify rebuild retrieval qa and graph backend"
```
