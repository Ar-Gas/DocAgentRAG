# DocAgent Modular Retrieval QA Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild retrieval, QA, and graph capabilities as explicit modules that use the LightRAG gateway for semantic operations and local identifiers for citations and preview anchors.

**Architecture:** Retrieval becomes a two-step workflow: semantic recall via LightRAG, then local enrichment and citation resolution via SQLite-backed blocks and document metadata. QA and graph reuse the same resolved evidence layer. Existing v1 endpoints stay alive through compatibility mapping until frontend v2 adoption is complete.

**Tech Stack:** FastAPI, httpx, pytest, asyncio, SSE streaming

---

## File Structure

**Files:**
- Create: `backend/app/modules/retrieval/api.py`
- Create: `backend/app/modules/retrieval/schemas.py`
- Create: `backend/app/modules/retrieval/service.py`
- Create: `backend/app/modules/retrieval/query_planner.py`
- Create: `backend/app/modules/retrieval/ranker.py`
- Create: `backend/app/modules/retrieval/citation_resolver.py`
- Create: `backend/app/modules/retrieval/contracts.py`
- Create: `backend/app/modules/retrieval/README.md`
- Create: `backend/app/modules/qa/api.py`
- Create: `backend/app/modules/qa/schemas.py`
- Create: `backend/app/modules/qa/service.py`
- Create: `backend/app/modules/qa/context_builder.py`
- Create: `backend/app/modules/qa/contracts.py`
- Create: `backend/app/modules/qa/README.md`
- Create: `backend/app/modules/graph/api.py`
- Create: `backend/app/modules/graph/schemas.py`
- Create: `backend/app/modules/graph/service.py`
- Create: `backend/app/modules/graph/contracts.py`
- Create: `backend/app/modules/graph/README.md`
- Modify: `backend/api/retrieval.py`
- Modify: `backend/api/qa.py`
- Modify: `backend/api/topics.py`
- Create: `backend/test/modules/retrieval/test_citation_resolver.py`
- Create: `backend/test/modules/retrieval/test_retrieval_service_contract.py`
- Create: `backend/test/modules/qa/test_qa_service_contract.py`
- Create: `backend/test/modules/graph/test_graph_service_contract.py`

---

### Task 1: Build Citation Resolution As The Shared Evidence Layer

**Files:**
- Create: `backend/app/modules/retrieval/citation_resolver.py`
- Create: `backend/test/modules/retrieval/test_citation_resolver.py`

- [ ] **Step 1: Write the failing citation resolver test**

Create `backend/test/modules/retrieval/test_citation_resolver.py` with:

```python
from app.modules.retrieval.citation_resolver import CitationResolver


def test_citation_resolver_maps_remote_result_to_local_ids():
    resolver = CitationResolver(
        block_lookup=lambda remote_id: {
            "document_id": "doc-1",
            "version_id": "ver-1",
            "block_id": "blk-1",
            "page_number": 3,
        }
    )

    result = resolver.resolve({"doc_id": "remote-1", "chunk_id": "remote-block-1", "text": "federated learning"})

    assert result["document_id"] == "doc-1"
    assert result["block_id"] == "blk-1"
    assert result["page_number"] == 3
```

- [ ] **Step 2: Run the citation resolver test and verify it fails**

Run: `cd backend && python -m pytest test/modules/retrieval/test_citation_resolver.py::test_citation_resolver_maps_remote_result_to_local_ids -v`
Expected: FAIL because the resolver does not exist yet.

- [ ] **Step 3: Implement the resolver**

Create `backend/app/modules/retrieval/citation_resolver.py` with:

```python
class CitationResolver:
    def __init__(self, block_lookup):
        self.block_lookup = block_lookup

    def resolve(self, payload: dict) -> dict:
        local = self.block_lookup(payload.get("chunk_id") or payload.get("doc_id"))
        return {
            "document_id": local["document_id"],
            "version_id": local["version_id"],
            "block_id": local["block_id"],
            "page_number": local.get("page_number"),
            "content": payload.get("text") or payload.get("content") or "",
            "score": payload.get("score") or 0.0,
        }
```

- [ ] **Step 4: Re-run the citation resolver test**

Run: `cd backend && python -m pytest test/modules/retrieval/test_citation_resolver.py::test_citation_resolver_maps_remote_result_to_local_ids -v`
Expected: PASS.

- [ ] **Step 5: Commit the shared evidence resolver**

```bash
git add backend/app/modules/retrieval/citation_resolver.py backend/test/modules/retrieval/test_citation_resolver.py
git commit -m "feat: add citation resolver for modular retrieval"
```

### Task 2: Build The Retrieval Module On Top Of LightRAG Gateway

**Files:**
- Create: `backend/app/modules/retrieval/api.py`
- Create: `backend/app/modules/retrieval/schemas.py`
- Create: `backend/app/modules/retrieval/service.py`
- Create: `backend/app/modules/retrieval/query_planner.py`
- Create: `backend/app/modules/retrieval/ranker.py`
- Create: `backend/app/modules/retrieval/contracts.py`
- Create: `backend/app/modules/retrieval/README.md`
- Create: `backend/test/modules/retrieval/test_retrieval_service_contract.py`

- [ ] **Step 1: Write the failing retrieval service test**

Create `backend/test/modules/retrieval/test_retrieval_service_contract.py` with:

```python
import pytest

from app.modules.retrieval.schemas import RetrievalQuery
from app.modules.retrieval.service import RetrievalService


class DummyGateway:
    async def search(self, request):
        return type(
            "SearchResult",
            (),
            {
                "items": [
                    type("Item", (), {"remote_document_id": "remote-1", "content": "federated learning", "score": 0.9, "metadata": {"chunk_id": "c-1"}})
                ]
            },
        )


@pytest.mark.asyncio
async def test_retrieval_service_returns_localized_results():
    service = RetrievalService(
        lightrag_gateway=DummyGateway(),
        citation_resolver=lambda item: {"document_id": "doc-1", "block_id": "blk-1", "content": item.content, "score": item.score},
    )

    result = await service.search(RetrievalQuery(query="federated learning"))

    assert result.total == 1
    assert result.items[0].document_id == "doc-1"
```

- [ ] **Step 2: Run the retrieval service test and verify it fails**

Run: `cd backend && python -m pytest test/modules/retrieval/test_retrieval_service_contract.py::test_retrieval_service_returns_localized_results -v`
Expected: FAIL because the retrieval module does not exist yet.

- [ ] **Step 3: Implement the retrieval module**

Create `backend/app/modules/retrieval/schemas.py` with:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalQuery:
    query: str
    mode: str = "hybrid"
    top_k: int = 10


@dataclass(frozen=True)
class RetrievalItem:
    document_id: str
    block_id: str
    content: str
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    total: int
    items: list[RetrievalItem]
```

Create `backend/app/modules/retrieval/service.py` with a `search` method that calls the LightRAG gateway and localizes each result through the resolver.

Expose `backend/app/modules/retrieval/api.py` under `/api/v2/retrieval/search`.

- [ ] **Step 4: Re-run the retrieval service test**

Run: `cd backend && python -m pytest test/modules/retrieval/test_retrieval_service_contract.py::test_retrieval_service_returns_localized_results -v`
Expected: PASS.

- [ ] **Step 5: Commit the retrieval module**

```bash
git add backend/app/modules/retrieval backend/test/modules/retrieval/test_retrieval_service_contract.py
git commit -m "feat: add modular retrieval service backed by lightrag"
```

### Task 3: Build The QA Module With Streaming Contracts

**Files:**
- Create: `backend/app/modules/qa/api.py`
- Create: `backend/app/modules/qa/schemas.py`
- Create: `backend/app/modules/qa/service.py`
- Create: `backend/app/modules/qa/context_builder.py`
- Create: `backend/app/modules/qa/contracts.py`
- Create: `backend/app/modules/qa/README.md`
- Create: `backend/test/modules/qa/test_qa_service_contract.py`
- Modify: `backend/api/qa.py`

- [ ] **Step 1: Write the failing QA service test**

Create `backend/test/modules/qa/test_qa_service_contract.py` with:

```python
import pytest

from app.modules.qa.schemas import QARequest
from app.modules.qa.service import QAService


class DummyRetrievalService:
    async def search(self, query):
        return type("Result", (), {"items": [type("Item", (), {"document_id": "doc-1", "block_id": "blk-1", "content": "federated learning improves privacy", "score": 0.9})], "total": 1})


@pytest.mark.asyncio
async def test_qa_service_returns_answer_with_citations():
    service = QAService(retrieval_service=DummyRetrievalService(), llm_gateway=None)

    answer = await service.answer(QARequest(query="What improves privacy?", top_k=3, session_id="s-1"))

    assert answer.citations[0]["document_id"] == "doc-1"
    assert answer.session_id == "s-1"
```

- [ ] **Step 2: Run the QA service test and verify it fails**

Run: `cd backend && python -m pytest test/modules/qa/test_qa_service_contract.py::test_qa_service_returns_answer_with_citations -v`
Expected: FAIL because the module does not exist yet.

- [ ] **Step 3: Implement the QA module**

Create `backend/app/modules/qa/schemas.py` with `QARequest`, `QAAnswer`, and `QAStreamEvent` dataclasses. Implement `QAService.answer` to use retrieval results as context and return an answer object with citation payloads. Update `backend/api/qa.py` to delegate to the new service while preserving current response semantics.

- [ ] **Step 4: Re-run the QA service test**

Run: `cd backend && python -m pytest test/modules/qa/test_qa_service_contract.py::test_qa_service_returns_answer_with_citations -v`
Expected: PASS.

- [ ] **Step 5: Commit the QA module**

```bash
git add backend/app/modules/qa backend/api/qa.py backend/test/modules/qa/test_qa_service_contract.py
git commit -m "feat: add modular qa service and streaming contract"
```

### Task 4: Build The Graph Module And Compatibility Mapping

**Files:**
- Create: `backend/app/modules/graph/api.py`
- Create: `backend/app/modules/graph/schemas.py`
- Create: `backend/app/modules/graph/service.py`
- Create: `backend/app/modules/graph/contracts.py`
- Create: `backend/app/modules/graph/README.md`
- Create: `backend/test/modules/graph/test_graph_service_contract.py`
- Modify: `backend/api/topics.py`
- Modify: `backend/api/retrieval.py`

- [ ] **Step 1: Write the failing graph service test**

Create `backend/test/modules/graph/test_graph_service_contract.py` with:

```python
import pytest

from app.modules.graph.service import GraphService


class DummyGateway:
    async def graph(self, request):
        return type("GraphResult", (), {"nodes": [{"id": "n-1", "label": "联邦学习"}], "edges": [{"source": "n-1", "target": "n-2", "label": "improves"}]})


@pytest.mark.asyncio
async def test_graph_service_returns_nodes_and_edges():
    service = GraphService(lightrag_gateway=DummyGateway())

    result = await service.get_graph(label="联邦学习")

    assert result.nodes[0]["label"] == "联邦学习"
    assert result.edges[0]["label"] == "improves"
```

- [ ] **Step 2: Run the graph service test and verify it fails**

Run: `cd backend && python -m pytest test/modules/graph/test_graph_service_contract.py::test_graph_service_returns_nodes_and_edges -v`
Expected: FAIL because the graph module does not exist yet.

- [ ] **Step 3: Implement the graph module and v1 compatibility**

Implement `GraphService.get_graph`, expose `/api/v2/graph`, and update `backend/api/topics.py` to delegate to the modular service while preserving current route behavior.

- [ ] **Step 4: Re-run the graph service test**

Run: `cd backend && python -m pytest test/modules/graph/test_graph_service_contract.py::test_graph_service_returns_nodes_and_edges -v`
Expected: PASS.

- [ ] **Step 5: Commit the graph module**

```bash
git add backend/app/modules/graph backend/api/topics.py backend/api/retrieval.py backend/test/modules/graph/test_graph_service_contract.py
git commit -m "feat: add modular graph service and retrieval compatibility"
```

## Verification

- [ ] Run: `cd backend && python -m pytest test/modules/retrieval test/modules/qa test/modules/graph -v`
- [ ] Run: `cd backend && python -m pytest test/test_retrieval_service_api.py test/test_qa_service_api.py test/test_topics_lightrag_api.py -v`
- [ ] Manually confirm:

```text
1. v2 retrieval returns local document and block identifiers.
2. v2 QA returns citations that can open a specific document block.
3. v2 graph returns stable nodes and edges from LightRAG-backed data.
4. Existing v1 retrieval, QA, and topics routes still respond.
```
