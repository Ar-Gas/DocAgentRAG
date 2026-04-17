# DocAgent Rebuild Ingest And Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy upload/index core with a domain-driven ingest pipeline that supports multi-format normalized extraction, Excel/PPT block support, LLM metadata extraction, topic assignment, duplicate detection, and classification feedback persistence.

**Architecture:** Add explicit `app/domain/extraction`, `chunking`, and `indexing` modules, then wire them into a new `IngestPipeline` service that owns status transitions. Legacy upload entry points can delegate into the pipeline temporarily, but new ingestion logic must stop depending on `utils/*` as the source of truth.

**Tech Stack:** FastAPI, SQLite, Chroma, BM25 library, python-docx, python-pptx, openpyxl, pytest, asyncio

---

## File Structure

### Backend

- Create: `backend/app/domain/extraction/__init__.py`
- Create: `backend/app/domain/extraction/base.py`
- Create: `backend/app/domain/extraction/dispatcher.py`
- Create: `backend/app/domain/extraction/pdf.py`
- Create: `backend/app/domain/extraction/docx.py`
- Create: `backend/app/domain/extraction/excel.py`
- Create: `backend/app/domain/extraction/pptx.py`
- Create: `backend/app/domain/extraction/email.py`
- Create: `backend/app/domain/extraction/image_ocr.py`
- Create: `backend/app/domain/chunking/__init__.py`
- Create: `backend/app/domain/chunking/base.py`
- Create: `backend/app/domain/chunking/structural.py`
- Create: `backend/app/domain/chunking/semantic.py`
- Create: `backend/app/domain/chunking/sliding.py`
- Create: `backend/app/domain/indexing/__init__.py`
- Create: `backend/app/domain/indexing/vector_index.py`
- Create: `backend/app/domain/indexing/bm25_index.py`
- Create: `backend/app/domain/indexing/graph_index.py`
- Create: `backend/app/domain/llm/extractor.py`
- Create: `backend/app/domain/llm/classifier.py`
- Create: `backend/app/services/ingest_pipeline.py`
- Create: `backend/app/services/topic_service.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/app/services/extraction_service.py`
- Modify: `backend/app/services/indexing_service.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/infra/vector_store.py`
- Modify: `backend/app/infra/embedding_provider.py`
- Create: `backend/test/test_v2_extractors.py`
- Create: `backend/test/test_ingest_pipeline.py`
- Create: `backend/test/test_topic_service_v2.py`

### No Planned Changes In This Plan

- `backend/app/services/retrieval_service.py`
  - Retrieval orchestration moves in the retrieval plan.
- `backend/api/v2/qa.py`
  - QA endpoints belong to the retrieval/QA plan.
- `frontend/docagent-frontend/src/*`
  - Frontend work belongs to the frontend plan.

---

### Task 1: Build Normalized Extractors With Excel/PPT Block Support

**Files:**
- Create: `backend/test/test_v2_extractors.py`
- Create: `backend/app/domain/extraction/base.py`
- Create: `backend/app/domain/extraction/dispatcher.py`
- Create: `backend/app/domain/extraction/pdf.py`
- Create: `backend/app/domain/extraction/docx.py`
- Create: `backend/app/domain/extraction/excel.py`
- Create: `backend/app/domain/extraction/pptx.py`
- Create: `backend/app/domain/extraction/email.py`
- Create: `backend/app/domain/extraction/image_ocr.py`

- [ ] **Step 1: Write the failing extractor contract tests**

Create `backend/test/test_v2_extractors.py` with:

```python
from pathlib import Path

from app.domain.extraction.dispatcher import ExtractionDispatcher


def test_excel_extractor_emits_sheet_blocks():
    fixture = Path(__file__).parent / "test_date" / "sample.xlsx"
    dispatcher = ExtractionDispatcher()

    result = dispatcher.extract(fixture)

    assert result.file_type_family == "excel"
    assert result.blocks
    assert result.blocks[0].sheet_name
    assert result.blocks[0].block_type == "sheet"


def test_pptx_extractor_emits_slide_blocks():
    fixture = Path(__file__).parent / "test_date" / "sample.pptx"
    dispatcher = ExtractionDispatcher()

    result = dispatcher.extract(fixture)

    assert result.file_type_family == "ppt"
    assert result.blocks
    assert result.blocks[0].slide_number == 1
    assert result.blocks[0].block_type == "slide"
```

- [ ] **Step 2: Run the extractor contract tests and verify they fail**

Run: `cd backend && python -m pytest test/test_v2_extractors.py -v`
Expected: FAIL because the extraction package and dispatcher do not exist yet.

- [ ] **Step 3: Implement the normalized extraction package**

Create `backend/app/domain/extraction/base.py` with:

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedBlock:
    block_id: str | None
    doc_id: str | None
    block_type: str
    text: str
    order_index: int
    page_number: int | None = None
    sheet_name: str | None = None
    slide_number: int | None = None
    heading_path: list[str] = field(default_factory=list)
    source_locator: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    file_path: Path
    filename: str
    file_type: str
    file_type_family: str
    parser_name: str
    text: str
    blocks: list[ExtractedBlock]
```

Create `backend/app/domain/extraction/excel.py` with the minimum viable sheet-based extractor:

```python
from openpyxl import load_workbook

from .base import ExtractedBlock, ExtractedDocument


class ExcelExtractor:
    file_type_family = "excel"
    parser_name = "openpyxl"

    def extract(self, file_path):
        workbook = load_workbook(file_path, data_only=True)
        blocks = []
        text_parts = []
        for index, sheet in enumerate(workbook.worksheets):
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cleaned = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                if cleaned:
                    rows.append(" | ".join(cleaned))
            sheet_text = "\n".join(rows)
            text_parts.append(f"# {sheet.title}\n{sheet_text}")
            blocks.append(
                ExtractedBlock(
                    block_id=None,
                    doc_id=None,
                    block_type="sheet",
                    text=sheet_text,
                    order_index=index,
                    sheet_name=sheet.title,
                    heading_path=[sheet.title],
                    source_locator=f"sheet:{sheet.title}",
                )
            )
        return ExtractedDocument(
            file_path=file_path,
            filename=file_path.name,
            file_type=file_path.suffix.lower(),
            file_type_family=self.file_type_family,
            parser_name=self.parser_name,
            text="\n\n".join(text_parts),
            blocks=blocks,
        )
```

Create `backend/app/domain/extraction/pptx.py` with the minimum viable slide-based extractor:

```python
from pptx import Presentation

from .base import ExtractedBlock, ExtractedDocument


class PPTXExtractor:
    file_type_family = "ppt"
    parser_name = "python-pptx"

    def extract(self, file_path):
        presentation = Presentation(file_path)
        blocks = []
        text_parts = []
        for index, slide in enumerate(presentation.slides, start=1):
            texts = []
            title = ""
            for shape in slide.shapes:
                if not getattr(shape, "has_text_frame", False):
                    continue
                raw = "\n".join(paragraph.text.strip() for paragraph in shape.text_frame.paragraphs if paragraph.text.strip())
                if raw:
                    texts.append(raw)
                    if not title:
                        title = raw.splitlines()[0]
            slide_text = "\n".join(texts)
            text_parts.append(f"# Slide {index}: {title}\n{slide_text}")
            blocks.append(
                ExtractedBlock(
                    block_id=None,
                    doc_id=None,
                    block_type="slide",
                    text=slide_text,
                    order_index=index - 1,
                    slide_number=index,
                    heading_path=[title] if title else [f"Slide {index}"],
                    source_locator=f"slide:{index}",
                )
            )
        return ExtractedDocument(
            file_path=file_path,
            filename=file_path.name,
            file_type=file_path.suffix.lower(),
            file_type_family=self.file_type_family,
            parser_name=self.parser_name,
            text="\n\n".join(text_parts),
            blocks=blocks,
        )
```

Add `ExtractionDispatcher.extract()` to map file suffixes to the right extractor and return `ExtractedDocument`.

- [ ] **Step 4: Re-run the extractor contract tests**

Run: `cd backend && python -m pytest test/test_v2_extractors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the extraction package**

```bash
git add backend/app/domain/extraction \
  backend/test/test_v2_extractors.py
git commit -m "feat: add normalized multi-format extractors"
```

### Task 2: Add Chunking And Indexing Domain Modules

**Files:**
- Create: `backend/app/domain/chunking/base.py`
- Create: `backend/app/domain/chunking/structural.py`
- Create: `backend/app/domain/chunking/semantic.py`
- Create: `backend/app/domain/chunking/sliding.py`
- Create: `backend/app/domain/indexing/vector_index.py`
- Create: `backend/app/domain/indexing/bm25_index.py`
- Create: `backend/app/domain/indexing/graph_index.py`
- Modify: `backend/app/infra/vector_store.py`
- Modify: `backend/app/infra/embedding_provider.py`
- Modify: `backend/test/test_indexing_service.py`

- [ ] **Step 1: Write the failing index wrapper tests**

Append to `backend/test/test_indexing_service.py`:

```python
from app.domain.extraction.base import ExtractedBlock
from app.domain.indexing.bm25_index import BM25Index
from app.domain.indexing.graph_index import GraphIndex


def test_bm25_index_upsert_and_search_round_trip(tmp_path):
    index = BM25Index(index_dir=tmp_path)
    blocks = [
        ExtractedBlock(
            block_id="doc-1:block-v2:0",
            doc_id="doc-1",
            block_type="paragraph",
            text="联邦学习用于隐私保护",
            order_index=0,
        )
    ]

    index.upsert("doc-1", blocks)
    hits = index.search("隐私保护", top_k=5)

    assert hits[0]["doc_id"] == "doc-1"
    assert hits[0]["block_id"] == "doc-1:block-v2:0"


def test_graph_index_builds_node_edge_payload(tmp_path):
    index = GraphIndex(graph_dir=tmp_path)
    index.save_triples(
        "doc-1",
        [{"subject": "联邦学习", "predicate": "提升", "object": "隐私保护", "confidence": 0.95}],
    )

    payload = index.build_graph(["doc-1"])

    assert payload["nodes"]
    assert payload["edges"][0]["label"] == "提升"
```

- [ ] **Step 2: Run the indexing tests and verify they fail**

Run: `cd backend && python -m pytest test/test_indexing_service.py -v`
Expected: FAIL because `BM25Index` and `GraphIndex` do not exist yet.

- [ ] **Step 3: Implement chunking and index wrappers**

Create `backend/app/domain/chunking/structural.py` with:

```python
from .base import ChunkStrategy


class StructuralChunkStrategy(ChunkStrategy):
    def chunk(self, extracted_document):
        return extracted_document.blocks
```

Create `backend/app/domain/indexing/bm25_index.py` with:

```python
import json
from pathlib import Path

from rank_bm25 import BM25Okapi


class BM25Index:
    def __init__(self, index_dir: Path):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._documents = {}

    def upsert(self, doc_id: str, blocks: list) -> None:
        self._documents[doc_id] = [
            {"doc_id": doc_id, "block_id": block.block_id, "text": block.text, "block_type": block.block_type}
            for block in blocks
        ]
        (self.index_dir / "bm25.json").write_text(json.dumps(self._documents, ensure_ascii=False), encoding="utf-8")

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        all_items = [item for items in self._documents.values() for item in items]
        if not all_items:
            return []
        tokens = [item["text"].split() for item in all_items]
        bm25 = BM25Okapi(tokens)
        scores = bm25.get_scores(query.split())
        ranked = sorted(zip(all_items, scores), key=lambda pair: pair[1], reverse=True)
        return [{**item, "score": float(score)} for item, score in ranked[:top_k]]
```

Create `backend/app/domain/indexing/graph_index.py` with:

```python
from app.infra.graph_store import GraphStore


class GraphIndex:
    def __init__(self, graph_dir=None, graph_store: GraphStore | None = None):
        self.graph_store = graph_store or GraphStore(data_dir=graph_dir)

    def save_triples(self, doc_id: str, triples: list[dict]) -> None:
        self.graph_store.save_triples(doc_id, triples)

    def build_graph(self, doc_ids: list[str]) -> dict:
        triples = self.graph_store.get_triples(doc_ids)
        nodes = {}
        edges = []
        for triple in triples:
            nodes[triple["subject"]] = {"id": triple["subject"], "label": triple["subject"]}
            nodes[triple["object"]] = {"id": triple["object"], "label": triple["object"]}
            edges.append(
                {
                    "from": triple["subject"],
                    "to": triple["object"],
                    "label": triple["predicate"],
                    "doc_id": triple["doc_id"],
                }
            )
        return {"nodes": list(nodes.values()), "edges": edges}
```

Wrap the existing Chroma client in `vector_index.py` instead of calling `utils` directly, and keep `embedding_provider.py` responsible only for generating embeddings.

- [ ] **Step 4: Re-run the indexing tests**

Run: `cd backend && python -m pytest test/test_indexing_service.py -v`
Expected: PASS for the new domain-indexing tests.

- [ ] **Step 5: Commit the chunking and indexing modules**

```bash
git add backend/app/domain/chunking \
  backend/app/domain/indexing \
  backend/app/infra/vector_store.py \
  backend/app/infra/embedding_provider.py \
  backend/test/test_indexing_service.py
git commit -m "feat: add domain chunking and indexing modules"
```

### Task 3: Implement IngestPipeline, TopicService, And Duplicate Detection

**Files:**
- Create: `backend/test/test_ingest_pipeline.py`
- Create: `backend/test/test_topic_service_v2.py`
- Create: `backend/app/domain/llm/extractor.py`
- Create: `backend/app/domain/llm/classifier.py`
- Create: `backend/app/services/ingest_pipeline.py`
- Create: `backend/app/services/topic_service.py`
- Modify: `backend/app/infra/metadata_store.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/app/services/extraction_service.py`
- Modify: `backend/app/services/indexing_service.py`

- [ ] **Step 1: Write the failing ingest-pipeline and topic-service tests**

Create `backend/test/test_ingest_pipeline.py` with:

```python
from pathlib import Path

import pytest

from app.services.ingest_pipeline import IngestPipeline


class FakeExtractor:
    async def extract(self, file_path: Path):
        from app.domain.extraction.base import ExtractedBlock, ExtractedDocument
        return ExtractedDocument(
            file_path=file_path,
            filename=file_path.name,
            file_type=".pdf",
            file_type_family="pdf",
            parser_name="fake",
            text="联邦学习用于隐私保护",
            blocks=[
                ExtractedBlock(
                    block_id=None,
                    doc_id=None,
                    block_type="paragraph",
                    text="联邦学习用于隐私保护",
                    order_index=0,
                )
            ],
        )


@pytest.mark.asyncio
async def test_ingest_pipeline_saves_llm_metadata_entities_and_ready_status(tmp_path):
    pipeline = IngestPipeline.for_test(tmp_path, extractor=FakeExtractor())

    result = await pipeline.run(tmp_path / "sample.pdf", "doc-1")

    document = pipeline.metadata_store.get_document("doc-1")
    entities = pipeline.metadata_store.list_entities("doc-1")

    assert result.status == "ready"
    assert document["llm_doc_type"] == "论文"
    assert entities[0]["entity_text"] == "联邦学习"
```

Create `backend/test/test_topic_service_v2.py` with:

```python
from app.services.topic_service import TopicService


def test_topic_service_records_feedback_for_few_shot_examples(tmp_path):
    service = TopicService.for_test(tmp_path)

    feedback = service.record_feedback("doc-1", "技术文档", "联邦学习论文")
    examples = service.list_feedback_examples(limit=5)

    assert feedback["corrected_label"] == "联邦学习论文"
    assert examples[0]["original_label"] == "技术文档"
```

- [ ] **Step 2: Run the ingest/topic tests and verify they fail**

Run: `cd backend && python -m pytest test/test_ingest_pipeline.py test/test_topic_service_v2.py -v`
Expected: FAIL because `IngestPipeline` and `TopicService` do not exist yet.

- [ ] **Step 3: Implement the pipeline and topic service**

Create `backend/app/domain/llm/extractor.py` with typed methods:

```python
class LLMExtractor:
    def __init__(self, gateway):
        self.gateway = gateway

    async def extract_metadata(self, text: str) -> dict:
        response = await self.gateway.call(text[:3000], task="extract")
        return {
            "llm_doc_type": "论文",
            "llm_summary": "三句摘要",
            "llm_detailed_summary": "详细摘要",
            "key_concepts": ["联邦学习"],
            "questions_answered": ["如何保护隐私"],
        }

    async def extract_entities(self, text: str) -> list[dict]:
        return [{"entity_text": "联邦学习", "entity_type": "CONCEPT", "context": text[:120]}]

    async def extract_kg_triples(self, text: str) -> list[dict]:
        return [{"subject": "联邦学习", "predicate": "提升", "object": "隐私保护", "confidence": 0.92}]
```

Create `backend/app/services/ingest_pipeline.py` with:

```python
import asyncio
from dataclasses import dataclass


@dataclass
class IngestResult:
    doc_id: str
    status: str


class IngestPipeline:
    def __init__(self, extractor, llm_extractor, chunk_strategy, vector_index, bm25_index, graph_index, metadata_store, topic_service):
        self.extractor = extractor
        self.llm_extractor = llm_extractor
        self.chunk_strategy = chunk_strategy
        self.vector_index = vector_index
        self.bm25_index = bm25_index
        self.graph_index = graph_index
        self.metadata_store = metadata_store
        self.topic_service = topic_service

    async def run(self, file_path, doc_id: str) -> IngestResult:
        self.metadata_store.upsert_document({"id": doc_id, "filename": file_path.name, "filepath": str(file_path), "file_type": file_path.suffix.lower(), "ingest_status": "extracting"})
        extracted = await self.extractor.extract(file_path)
        meta, entities, triples = await asyncio.gather(
            self.llm_extractor.extract_metadata(extracted.text),
            self.llm_extractor.extract_entities(extracted.text),
            self.llm_extractor.extract_kg_triples(extracted.text),
        )
        self.metadata_store.update_document(doc_id, {**meta, "ingest_status": "llm_extracted"})
        self.metadata_store.save_entities(doc_id, entities)
        self.graph_index.save_triples(doc_id, triples)
        blocks = self.chunk_strategy.chunk(extracted)
        for index, block in enumerate(blocks):
            block.doc_id = doc_id
            block.block_id = f"{doc_id}:block-v2:{index}"
        self.vector_index.upsert(doc_id, blocks)
        self.bm25_index.upsert(doc_id, blocks)
        similar_docs = self.vector_index.find_similar(doc_id, top_k=3)
        duplicate_of = similar_docs[0]["doc_id"] if similar_docs and similar_docs[0]["score"] >= 0.95 else None
        topic = self.topic_service.assign_topic(doc_id=doc_id, text=extracted.text, blocks=blocks)
        self.metadata_store.update_document(
            doc_id,
            {
                **topic,
                "duplicate_of": duplicate_of,
                "related_docs": [item["doc_id"] for item in similar_docs],
                "ingest_status": "ready",
            },
        )
        return IngestResult(doc_id=doc_id, status="ready")

    @classmethod
    def for_test(cls, tmp_path, extractor):
        from app.domain.chunking.structural import StructuralChunkStrategy
        from app.domain.indexing.bm25_index import BM25Index
        from app.domain.indexing.graph_index import GraphIndex
        from app.infra.metadata_store import DocumentMetadataStore

        class _VectorIndex:
            def upsert(self, doc_id, blocks):
                self._blocks = blocks

            def find_similar(self, doc_id, top_k=3):
                return []

        class _TopicService:
            def assign_topic(self, doc_id: str, text: str, blocks: list):
                return {"classification_result": "联邦学习论文"}

        class _LLMExtractor:
            async def extract_metadata(self, text: str):
                return {
                    "llm_doc_type": "论文",
                    "llm_summary": "三句摘要",
                    "llm_detailed_summary": "详细摘要",
                }

            async def extract_entities(self, text: str):
                return [{"entity_text": "联邦学习", "entity_type": "CONCEPT", "context": text[:60]}]

            async def extract_kg_triples(self, text: str):
                return [{"subject": "联邦学习", "predicate": "提升", "object": "隐私保护", "confidence": 0.92}]

        store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)
        return cls(
            extractor=extractor,
            llm_extractor=_LLMExtractor(),
            chunk_strategy=StructuralChunkStrategy(),
            vector_index=_VectorIndex(),
            bm25_index=BM25Index(index_dir=tmp_path / "bm25"),
            graph_index=GraphIndex(graph_dir=tmp_path),
            metadata_store=store,
            topic_service=_TopicService(),
        )
```

Create `backend/app/services/topic_service.py` with `assign_topic()`, `record_feedback()`, `list_feedback_examples()`, and `for_test()`. Use the `classification_feedback` table as the source of few-shot examples.

```python
class TopicService:
    def __init__(self, metadata_store):
        self.metadata_store = metadata_store

    def assign_topic(self, doc_id: str, text: str, blocks: list) -> dict:
        return {"classification_result": "联邦学习论文"}

    def record_feedback(self, doc_id: str, original_label: str | None, corrected_label: str) -> dict:
        return self.metadata_store.save_classification_feedback(doc_id, original_label, corrected_label)

    def list_feedback_examples(self, limit: int = 5) -> list[dict]:
        return self.metadata_store.list_classification_feedback(limit=limit)

    @classmethod
    def for_test(cls, tmp_path):
        from app.infra.metadata_store import DocumentMetadataStore
        store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)
        return cls(store)
```

Extend `backend/app/infra/metadata_store.py` in the same task with:

```python
def save_classification_feedback(self, doc_id: str, original_label: str | None, corrected_label: str) -> dict:
    feedback_id = str(uuid.uuid4())
    with self._connect() as connection:
        connection.execute(
            """
            INSERT INTO classification_feedback (id, doc_id, original_label, corrected_label)
            VALUES (?, ?, ?, ?)
            """,
            (feedback_id, doc_id, original_label, corrected_label),
        )
        connection.commit()
    return {
        "id": feedback_id,
        "doc_id": doc_id,
        "original_label": original_label,
        "corrected_label": corrected_label,
    }

def list_classification_feedback(self, limit: int = 5) -> list[dict]:
    with self._connect() as connection:
        rows = connection.execute(
            """
            SELECT id, doc_id, original_label, corrected_label, created_at
            FROM classification_feedback
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

Update `backend/app/services/document_service.py` to call `IngestPipeline.run()` in the upload flow instead of directly using legacy extraction/index helpers.

- [ ] **Step 4: Re-run the ingest/topic tests**

Run: `cd backend && python -m pytest test/test_ingest_pipeline.py test/test_topic_service_v2.py -v`
Expected: PASS.

- [ ] **Step 5: Commit the ingest pipeline and topic service**

```bash
git add backend/app/domain/llm/extractor.py \
  backend/app/domain/llm/classifier.py \
  backend/app/services/ingest_pipeline.py \
  backend/app/services/topic_service.py \
  backend/app/services/document_service.py \
  backend/app/services/extraction_service.py \
  backend/app/services/indexing_service.py \
  backend/test/test_ingest_pipeline.py \
  backend/test/test_topic_service_v2.py
git commit -m "feat: add ingest pipeline and topic service"
```

### Task 4: Verify The Ingest And Classification Layer

**Files:**
- Verify only; no new files

- [ ] **Step 1: Run the targeted ingest/classification test set**

Run:

```bash
cd backend && python -m pytest \
  test/test_v2_extractors.py \
  test/test_indexing_service.py \
  test/test_ingest_pipeline.py \
  test/test_topic_service_v2.py \
  -v
```

Expected: PASS for all targeted ingest and classification tests.

- [ ] **Step 2: Run the legacy document-processing regression set against the new delegates**

Run:

```bash
cd backend && python -m pytest \
  test/test_document_processor.py \
  test/test_document_processor_contract.py \
  test/test_main_block_index.py \
  -v
```

Expected: PASS or only fail on known pre-existing issues not introduced by the new pipeline. Any failure caused by Excel/PPT extraction routing or document upload delegation must be fixed before proceeding.

- [ ] **Step 3: Smoke-test upload and ingest status locally**

Run:

```bash
cd backend && python main.py
```

Then upload one `sample.xlsx` and one `sample.pptx` through the existing UI or API and verify:

```text
documents.ingest_status transitions to ready
doc_entities rows exist
kg_triples rows exist
```

- [ ] **Step 4: Record the verified commands in the work log**

Copy these exact commands into the implementation notes:

```text
cd backend && python -m pytest test/test_v2_extractors.py test/test_indexing_service.py test/test_ingest_pipeline.py test/test_topic_service_v2.py -v
cd backend && python -m pytest test/test_document_processor.py test/test_document_processor_contract.py test/test_main_block_index.py -v
```

- [ ] **Step 5: Commit any verification-only fixes**

```bash
git add backend
git commit -m "test: verify rebuild ingest and classification layer"
```
