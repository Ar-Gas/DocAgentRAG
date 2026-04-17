# Excluded Document Fallback Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every document receives a compliant `classification_result` during topic-tree rebuild: vector-excluded but usable documents get a fallback label, and unusable/error documents are isolated as `Error` instead of polluting semantic topics or remaining `<NULL>`.

**Architecture:** Extract single-document label resolution into a shared resolver used by both `ClassificationService` and `TopicTreeService`. `TopicClustering` will emit exclusion reasons, and `TopicTreeService` will append dedicated fallback branches for excluded documents instead of dropping them from the tree. Semantic clusters remain reserved for vector-ready, content-usable documents.

**Tech Stack:** Python 3.12, FastAPI service layer, Chroma block embeddings, sqlite-backed metadata store, pytest

---

## File Structure

- Create: `backend/app/services/document_label_resolver.py`
  Responsibility: shared source-text loading, unusable-content detection, LLM-backed single-document label resolution, heuristic fallback normalization.
- Modify: `backend/app/services/classification_service.py`
  Responsibility: replace duplicated source-text/error detection with the shared resolver so single-document classification and topic-tree rebuild use the same contract.
- Modify: `backend/app/services/topic_clustering.py`
  Responsibility: annotate excluded documents with structured reasons such as `unusable_content`, `missing_vector`, and `dimension_mismatch`.
- Modify: `backend/app/services/topic_tree_service.py`
  Responsibility: create fallback topic branches for excluded documents, bump artifact contract, and persist fallback assignments instead of writing `<NULL>`.
- Create: `backend/test/test_document_label_resolver.py`
  Responsibility: unit-test resolver behavior for usable text, parser failures, HTML interstitials, and normalized LLM labels.
- Modify: `backend/test/test_topic_tree_service.py`
  Responsibility: verify excluded documents enter fallback branches and no longer disappear from the tree.
- Modify: `backend/test/test_classification_topic_tree_contract.py`
  Responsibility: verify rebuild-time classification no longer leaves excluded usable documents unclassified.

### Task 1: Lock the fallback-tree contract with failing tests

**Files:**
- Modify: `backend/test/test_topic_tree_service.py`
- Modify: `backend/test/test_classification_topic_tree_contract.py`
- Test: `backend/test/test_topic_tree_service.py`
- Test: `backend/test/test_classification_topic_tree_contract.py`

- [ ] **Step 1: Write the failing topic-tree regression tests**

```python
def test_build_topic_tree_adds_fallback_topics_for_excluded_documents(monkeypatch):
    updates = []

    def documents():
        return [
            {"id": "doc-1", "filename": "audit-plan.pdf", "file_type": ".pdf", "created_at_iso": "2026-04-01T10:00:00"},
            {"id": "doc-2", "filename": "labor-contract.docx", "file_type": ".docx", "created_at_iso": "2026-04-02T10:00:00"},
            {"id": "doc-3", "filename": "broken.docx", "file_type": ".docx", "created_at_iso": "2026-04-03T10:00:00"},
        ]

    class FakeTopicClusteringWithExcluded:
        def __init__(self, *args, **kwargs):
            pass

        def build_document_vectors(self, docs):
            return (
                [{**docs[0], "vector": [1.0, 0.0]}],
                [
                    {**docs[1], "exclude_reason": "missing_vector"},
                    {**docs[2], "exclude_reason": "unusable_content"},
                ],
            )

        def cluster_documents(self, docs, level):
            return [{"documents": docs, "representatives": docs[:1], "center": [1.0, 0.0]}]

    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", documents)
    monkeypatch.setattr(topic_tree_service_module, "get_document_content_record", lambda document_id: {
        "doc-1": {"preview_content": "年度审计计划与整改安排"},
        "doc-2": {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
        "doc-3": {"preview_content": "Word处理失败: Package not found at '/tmp/broken.docx'"},
    }[document_id])
    monkeypatch.setattr(topic_tree_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: updates.append((document_id, updated_info)) or True)
    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", lambda document_id, doc_info: {
        "doc-2": {"label": "劳动合同", "source_text": "甲方与乙方签署劳动合同，并约定试用期与薪酬。", "is_error": False, "source": "llm"},
        "doc-3": {"label": "Error", "source_text": "", "is_error": True, "source": "error_text"},
    }[document_id])

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    fallback_parent = next(topic for topic in tree["topics"] if topic["label"] == "兜底分类")
    error_parent = next(topic for topic in tree["topics"] if topic["label"] == "异常文档")

    assert [child["label"] for child in fallback_parent["children"]] == ["劳动合同"]
    assert [child["label"] for child in error_parent["children"]] == ["Error"]
    assert fallback_parent["children"][0]["documents"][0]["document_id"] == "doc-2"
    assert error_parent["children"][0]["documents"][0]["document_id"] == "doc-3"
    assert any(document_id == "doc-2" and payload["classification_result"] == "劳动合同" for document_id, payload in updates)
    assert any(document_id == "doc-3" and payload["classification_result"] == "Error" for document_id, payload in updates)


def test_rebuild_contract_no_longer_leaves_excluded_usable_documents_unclassified(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "labor-contract.docx",
            "classification_result": None,
            "preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。",
        },
    )

    service = ClassificationService()
    service.topic_tree_service = Mock(
        classify_document=Mock(
            return_value={
                "document_id": "doc-2",
                "topic_id": "topic-fallback-1",
                "topic_label": "劳动合同",
                "topic_path": ["兜底分类", "劳动合同"],
                "confidence": 1.0,
            }
        )
    )

    payload = service.get_document_multi_level_info("doc-2")

    assert payload["topic_label"] == "劳动合同"
    assert payload["topic_path"] == ["兜底分类", "劳动合同"]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/test/test_topic_tree_service.py backend/test/test_classification_topic_tree_contract.py -k "fallback_topics or unclassified" -v`

Expected: FAIL because `TopicTreeService` does not create `兜底分类/异常文档` branches and excluded documents still sync to `classification_result=None`.

- [ ] **Step 3: Implement the minimal tree contract to make the tests meaningful**

```python
# backend/app/services/topic_tree_service.py
class TopicTreeService:
    artifact_name = "topic_tree"
    schema_version = 3
    generation_method = "doc_embedding_cluster+fallback_label_contract"
```

```python
# backend/app/services/topic_tree_service.py
def _build_payload(self, topics, *, total_documents, clustered_documents, excluded_documents):
    return {
        "schema_version": self.schema_version,
        "generated_at": datetime.now().isoformat(),
        "total_documents": total_documents,
        "clustered_documents": clustered_documents,
        "excluded_documents": excluded_documents,
        "topic_count": len(topics),
        "generation_method": self.generation_method,
        "topics": topics,
    }
```

- [ ] **Step 4: Run the focused tests again and keep them red until real fallback branches exist**

Run: `backend/.venv/bin/python -m pytest backend/test/test_topic_tree_service.py backend/test/test_classification_topic_tree_contract.py -k "fallback_topics or unclassified" -v`

Expected: still FAIL, but now against missing fallback implementation instead of the old artifact contract.

- [ ] **Step 5: Commit the red-test scaffold**

```bash
git add backend/test/test_topic_tree_service.py backend/test/test_classification_topic_tree_contract.py backend/app/services/topic_tree_service.py
git commit -m "test: lock fallback topic tree contract"
```

### Task 2: Extract shared single-document label resolution

**Files:**
- Create: `backend/app/services/document_label_resolver.py`
- Create: `backend/test/test_document_label_resolver.py`
- Modify: `backend/app/services/classification_service.py`
- Test: `backend/test/test_document_label_resolver.py`

- [ ] **Step 1: Write failing resolver unit tests**

```python
def test_resolve_document_label_uses_preview_or_full_content(monkeypatch):
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: {"preview_content": "", "full_content": "本协议约定劳动期限、薪酬与保密义务。"})

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "labor-contract.docx"
            assert text == "本协议约定劳动期限、薪酬与保密义务。"
            return "劳动合同"

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-2",
            {"id": "doc-2", "filename": "labor-contract.docx", "preview_content": ""},
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["is_error"] is False
    assert result["source"] == "llm"


def test_resolve_document_label_returns_error_for_parser_failure(monkeypatch):
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: None)

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-3",
            {"id": "doc-3", "filename": "broken.docx", "preview_content": "Word处理失败: Package not found at '/tmp/broken.docx'"},
            llm_gateway=None,
        )
    )

    assert result == {
        "label": "Error",
        "source_text": "",
        "is_error": True,
        "source": "error_text",
    }
```

- [ ] **Step 2: Run the resolver tests and verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/test/test_document_label_resolver.py -v`

Expected: FAIL with `ModuleNotFoundError` for `backend/app/services/document_label_resolver.py`.

- [ ] **Step 3: Implement the resolver and switch `ClassificationService` to it**

```python
# backend/app/services/document_label_resolver.py
from typing import Dict, List

from app.domain.classification_contract import (
    SPECIAL_ERROR_LABEL,
    first_usable_text,
    is_unusable_classification_text,
    normalize_classification_label,
)
from app.domain.llm.gateway import LLMGateway
from app.infra.repositories.document_content_repository import DocumentContentRepository
from config import DATA_DIR


def _document_content_repository() -> DocumentContentRepository:
    return DocumentContentRepository(data_dir=DATA_DIR)


def get_document_content_record(document_id: str):
    return _document_content_repository().get(document_id)


def source_text_candidates(document_id: str, doc_info: Dict) -> List[str]:
    content_record = get_document_content_record(document_id) or {}
    return [
        doc_info.get("preview_content") or "",
        content_record.get("preview_content") or "",
        content_record.get("full_content") or "",
        doc_info.get("full_content") or "",
        doc_info.get("content") or "",
    ]


def load_source_text(document_id: str, doc_info: Dict) -> str:
    return first_usable_text(source_text_candidates(document_id, doc_info))


def is_error_document(document_id: str, doc_info: Dict) -> bool:
    source_text = load_source_text(document_id, doc_info)
    if source_text:
        return False
    return any(
        is_unusable_classification_text(text)
        for text in source_text_candidates(document_id, doc_info)
        if str(text or "").strip()
    )


async def resolve_document_label(document_id: str, doc_info: Dict, llm_gateway: LLMGateway | None = None) -> Dict:
    source_text = load_source_text(document_id, doc_info)
    if is_error_document(document_id, doc_info):
        return {"label": SPECIAL_ERROR_LABEL, "source_text": "", "is_error": True, "source": "error_text"}

    gateway = llm_gateway or LLMGateway()
    label = normalize_classification_label(
        await gateway.classify(title=doc_info.get("filename", ""), text=source_text[:500])
    )
    if label:
        return {"label": label, "source_text": source_text, "is_error": False, "source": "llm"}

    fallback = normalize_classification_label(doc_info.get("filename", ""))
    return {"label": fallback or SPECIAL_ERROR_LABEL, "source_text": source_text, "is_error": fallback is None, "source": "heuristic"}
```

```python
# backend/app/services/classification_service.py
from app.services.document_label_resolver import (
    is_error_document,
    load_source_text,
    resolve_document_label,
)
```

```python
# backend/app/services/classification_service.py
label_result = await resolve_document_label(document_id, doc_info, llm_gateway=llm_gateway)
if label_result["is_error"]:
    self._persist_error_label(document_id)
    return SPECIAL_ERROR_LABEL
label_b = normalize_classification_label(label_result["label"])
source_text = label_result["source_text"]
```

- [ ] **Step 4: Run the resolver and classification tests to verify they pass**

Run: `backend/.venv/bin/python -m pytest backend/test/test_document_label_resolver.py backend/test/test_classification_topic_tree_contract.py -k "resolve_document_label or payload_field_is_absent or processing_failures" -v`

Expected: PASS, including the existing regression that `ClassificationService.classify_document()` reads `preview_content/full_content` instead of the nonexistent `payload` field.

- [ ] **Step 5: Commit the shared resolver extraction**

```bash
git add backend/app/services/document_label_resolver.py backend/app/services/classification_service.py backend/test/test_document_label_resolver.py backend/test/test_classification_topic_tree_contract.py
git commit -m "refactor: extract shared document label resolver"
```

### Task 3: Route excluded documents into fallback topic branches

**Files:**
- Modify: `backend/app/services/topic_clustering.py`
- Modify: `backend/app/services/topic_tree_service.py`
- Modify: `backend/test/test_topic_tree_service.py`
- Test: `backend/test/test_topic_tree_service.py`

- [ ] **Step 1: Write the failing implementation-level tests for exclusion reasons**

```python
def test_build_document_vectors_marks_unusable_content_as_excluded(monkeypatch):
    clustering = TopicClustering()

    monkeypatch.setattr(topic_clustering_module, "list_document_block_embeddings", lambda document_id: [[0.1, 0.2]])
    monkeypatch.setattr(topic_clustering_module, "embed_text", lambda text: [1.0, 0.0])
    monkeypatch.setattr(topic_clustering_module, "is_error_document", lambda document_id, doc_info: doc_info["document_id"] == "doc-error")

    prepared, excluded = clustering.build_document_vectors(
        [
            {"document_id": "doc-ok", "filename": "audit-plan.pdf", "summary_source": "年度审计计划"},
            {"document_id": "doc-error", "filename": "broken.docx", "summary_source": "Word处理失败"},
        ]
    )

    assert [item["document_id"] for item in prepared] == ["doc-ok"]
    assert excluded == [{"document_id": "doc-error", "filename": "broken.docx", "summary_source": "Word处理失败", "exclude_reason": "unusable_content"}]
```

- [ ] **Step 2: Run the topic-tree tests and verify they fail**

Run: `backend/.venv/bin/python -m pytest backend/test/test_topic_tree_service.py -k "fallback_topics or exclusion" -v`

Expected: FAIL because `TopicClustering` does not annotate exclusion reasons and `TopicTreeService` still drops excluded documents on sync.

- [ ] **Step 3: Implement exclusion reasons and fallback branches**

```python
# backend/app/services/topic_clustering.py
from app.services.document_label_resolver import is_error_document


def build_document_vectors(self, documents):
    prepared = []
    excluded = []

    for document in documents:
        if is_error_document(document.get("document_id", ""), document):
            excluded.append({**document, "exclude_reason": "unusable_content"})
            continue

        vector = self._derive_document_vector(document)
        if vector is None:
            excluded.append({**document, "exclude_reason": "missing_vector"})
            continue
        prepared.append({**document, "vector": vector})
```

```python
# backend/app/services/topic_tree_service.py
from app.services.document_label_resolver import resolve_document_label


async def _resolve_excluded_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for document in documents:
        result = await resolve_document_label(document["document_id"], document)
        rows.append({**document, "fallback_label": result["label"], "fallback_is_error": result["is_error"]})
    return rows


def _build_fallback_topics(self, excluded_documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normal_groups: Dict[str, List[Dict[str, Any]]] = {}
    error_documents: List[Dict[str, Any]] = []

    for document in excluded_documents:
        if document["fallback_is_error"]:
            error_documents.append(document)
            continue
        normal_groups.setdefault(document["fallback_label"], []).append(document)

    topics = []
    if normal_groups:
        topics.append(
            {
                "topic_id": "topic-fallback",
                "label": "兜底分类",
                "keywords": [],
                "document_count": sum(len(items) for items in normal_groups.values()),
                "documents": [],
                "children": [
                    {
                        "topic_id": f"topic-fallback-{index}",
                        "label": label,
                        "keywords": [],
                        "document_count": len(items),
                        "documents": [self._serialize_doc(item) for item in items],
                        "children": [],
                    }
                    for index, (label, items) in enumerate(sorted(normal_groups.items()), start=1)
                ],
            }
        )
    if error_documents:
        topics.append(
            {
                "topic_id": "topic-error",
                "label": "异常文档",
                "keywords": [],
                "document_count": len(error_documents),
                "documents": [],
                "children": [
                    {
                        "topic_id": "topic-error-1",
                        "label": "Error",
                        "keywords": [],
                        "document_count": len(error_documents),
                        "documents": [self._serialize_doc(item) for item in error_documents],
                        "children": [],
                    }
                ],
            }
        )
    return topics
```

```python
# backend/app/services/topic_tree_service.py
topics = self._build_topics(clusterable_documents)
resolved_excluded = asyncio.run(self._resolve_excluded_documents(excluded_documents))
topics.extend(self._build_fallback_topics(resolved_excluded))
```

- [ ] **Step 4: Run the topic-tree test suite and confirm the fallback branches work**

Run: `backend/.venv/bin/python -m pytest backend/test/test_topic_tree_service.py backend/test/test_classification_topic_tree_contract.py -v`

Expected: PASS, with excluded documents landing under `兜底分类/<label>` or `异常文档/Error` and no explicit sync path writing `classification_result=None` for usable excluded docs.

- [ ] **Step 5: Commit the topic-tree fallback routing**

```bash
git add backend/app/services/topic_clustering.py backend/app/services/topic_tree_service.py backend/test/test_topic_tree_service.py backend/test/test_classification_topic_tree_contract.py
git commit -m "feat: add fallback topics for excluded documents"
```

### Task 4: Verify with a local rebuild and data-quality checks

**Files:**
- Modify: `backend/test/test_topic_tree_service.py`
- Test: existing backend classification tests only

- [ ] **Step 1: Add the final regression that rebuild output no longer collapses into `Error + <NULL>`**

```python
def test_build_topic_tree_keeps_semantic_topics_and_fallback_topics_separate(monkeypatch):
    store = _patch_common_dependencies(monkeypatch)

    class FakeTopicClusteringMixed(FakeTopicClustering):
        def build_document_vectors(self, documents):
            return (
                [{**documents[0], "vector": [1.0, 0.0]}, {**documents[1], "vector": [2.0, 0.0]}],
                [{**documents[2], "exclude_reason": "missing_vector"}],
            )

    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringMixed, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", lambda document_id, doc_info: {"label": "供应商比价", "source_text": "供应商报价对比与合同条件评估。", "is_error": False, "source": "llm"})

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    labels = [topic["label"] for topic in tree["topics"]]
    assert "财务治理" in labels
    assert "兜底分类" in labels
    assert "异常文档" not in labels
```

- [ ] **Step 2: Run the full focused verification suite**

Run: `backend/.venv/bin/python -m pytest backend/test/test_document_label_resolver.py backend/test/test_topic_tree_service.py backend/test/test_classification_topic_tree_contract.py backend/test/test_topic_labeler_and_embedding_provider.py backend/test/test_classification_dependency_cleanup.py backend/test/test_llm_classifier_doubao.py -v`

Expected: PASS with no fallback-related failures.

- [ ] **Step 3: Rebuild the local topic tree and inspect the stored distribution**

Run:

```bash
cd backend
.venv/bin/python - <<'PY'
from app.services.topic_tree_service import TopicTreeService

tree = TopicTreeService().build_topic_tree(force_rebuild=True)
print({
    "schema_version": tree["schema_version"],
    "generation_method": tree["generation_method"],
    "topic_count": tree["topic_count"],
    "clustered_documents": tree["clustered_documents"],
    "excluded_documents": tree["excluded_documents"],
})
PY
```

Expected: exit `0`, with `schema_version == 3` and `generation_method == "doc_embedding_cluster+fallback_label_contract"`.

- [ ] **Step 4: Verify the sqlite payload no longer leaves usable documents as `<NULL>`**

Run:

```bash
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("backend/data/docagent.db")
cur = conn.cursor()

rows = list(cur.execute("""
select count(*), coalesce(classification_result, '<NULL>')
from documents
group by classification_result
order by count(*) desc, classification_result
"""))

bad_labels = {"处理失", "待整理事项", "文档内", "相关的", "--- 第 1 ", "Word处理失败"}
assert not any(label in bad_labels for _, label in rows), rows

usable_nulls = list(cur.execute("""
select id, filename
from documents
where classification_result is null
  and json_extract(payload, '$.preview_content') is not null
  and json_extract(payload, '$.preview_content') not like 'Word处理失败:%'
  and json_extract(payload, '$.preview_content') not like 'Excel处理失败:%'
  and json_extract(payload, '$.preview_content') not like 'PDF文档内容（使用MinerU提取）'
"""))

assert usable_nulls == [], usable_nulls
print(rows)
PY
```

Expected: PASS, and the remaining null rows are limited to genuinely empty/unparseable payloads that should be handled in a future ingest cleanup task.

- [ ] **Step 5: Commit the verification pass**

```bash
git add backend/test/test_topic_tree_service.py
git commit -m "test: verify fallback classification rebuild flow"
```
