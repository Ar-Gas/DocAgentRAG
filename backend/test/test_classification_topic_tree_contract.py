import asyncio
import json
import os
import sys

from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.classification as classification_api  # noqa: E402
import app.domain.llm.gateway as llm_gateway_module  # noqa: E402
import app.services.classification_service as classification_service_module  # noqa: E402
import app.services.document_label_resolver as resolver_module  # noqa: E402
import app.services.topic_tree_service as topic_tree_service_module  # noqa: E402
from app.services.classification_service import ClassificationService  # noqa: E402


def _topic_tree_payload():
    return {
        "schema_version": 3,
        "generated_at": "2026-04-16T10:00:00",
        "total_documents": 3,
        "clustered_documents": 3,
        "excluded_documents": 0,
        "topic_count": 1,
        "generation_method": "doc_embedding_cluster+fallback_label_contract",
        "topics": [
            {
                "topic_id": "topic-1",
                "label": "财务治理",
                "document_count": 3,
                "documents": [],
                "children": [
                    {
                        "topic_id": "topic-1-1",
                        "label": "年度审计",
                        "document_count": 2,
                        "documents": [
                            {
                                "document_id": "doc-1",
                                "filename": "audit-plan.pdf",
                                "file_type": ".pdf",
                                "classification_result": "旧标签A",
                                "created_at_iso": "2026-04-01T10:00:00",
                                "excerpt": "审计计划",
                                "keywords": [],
                            },
                            {
                                "document_id": "doc-2",
                                "filename": "audit-report.pdf",
                                "file_type": ".pdf",
                                "classification_result": "旧标签B",
                                "created_at_iso": "2026-04-02T10:00:00",
                                "excerpt": "审计报告",
                                "keywords": [],
                            },
                        ],
                        "children": [],
                    },
                    {
                        "topic_id": "topic-1-2",
                        "label": "供应商比价",
                        "document_count": 1,
                        "documents": [
                            {
                                "document_id": "doc-3",
                                "filename": "supplier.xlsx",
                                "file_type": ".xlsx",
                                "classification_result": "旧标签C",
                                "created_at_iso": "2026-04-03T10:00:00",
                                "excerpt": "供应商报价对比",
                                "keywords": [],
                            }
                        ],
                        "children": [],
                    },
                ],
            }
        ],
    }


def test_get_categories_prefers_taxonomy_labels(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_all_labels",
        lambda: [
            {
                "id": "hr.offer_approval",
                "label": "Offer审批",
                "path": ["人力资源", "招聘管理", "Offer审批"],
            },
            {
                "id": "finance.expense",
                "label": "费用报销",
                "path": ["财务管理", "报销管理", "费用报销"],
            },
        ],
    )

    service = ClassificationService()
    service.topic_tree_service = Mock(get_category_overview=Mock(return_value={"categories": ["旧分类"]}))

    payload = service.get_categories()

    assert payload == [
        {
            "id": "hr.offer_approval",
            "label": "Offer审批",
            "path": ["人力资源", "招聘管理", "Offer审批"],
            "domain": "人力资源",
        },
        {
            "id": "finance.expense",
            "label": "费用报销",
            "path": ["财务管理", "报销管理", "费用报销"],
            "domain": "财务管理",
        },
    ]
    service.topic_tree_service.get_category_overview.assert_not_called()


def test_get_categories_falls_back_to_topic_tree_when_taxonomy_empty(monkeypatch):
    monkeypatch.setattr(classification_service_module, "get_all_labels", lambda: [])

    service = ClassificationService()
    service.topic_tree_service = Mock(
        get_category_overview=Mock(
            return_value={
                "categories": ["供应商比价", "年度审计"],
                "document_count": {"年度审计": 2, "供应商比价": 1},
            }
        )
    )

    payload = service.get_categories()

    assert payload == {
        "categories": ["供应商比价", "年度审计"],
        "document_count": {"年度审计": 2, "供应商比价": 1},
    }
    service.topic_tree_service.get_category_overview.assert_called_once()


def test_get_documents_by_category_uses_topic_tree_membership_not_document_field(monkeypatch):
    service = ClassificationService()
    service.topic_tree_service = Mock(
        get_documents_by_topic=Mock(
            return_value={
                "category": "年度审计",
                "topic_id": "topic-1-1",
                "topic_path": ["财务治理", "年度审计"],
                "total": 2,
                "documents": [
                    {
                        "id": "doc-1",
                        "filename": "audit-plan.pdf",
                        "file_type": ".pdf",
                        "classification_result": "年度审计",
                    },
                    {
                        "id": "doc-2",
                        "filename": "audit-report.pdf",
                        "file_type": ".pdf",
                        "classification_result": "年度审计",
                    },
                ],
            }
        )
    )

    payload = service.get_documents_by_category("年度审计")

    assert payload["category"] == "年度审计"
    assert payload["total"] == 2
    assert [item["id"] for item in payload["documents"]] == ["doc-1", "doc-2"]
    assert payload["documents"][0]["classification_result"] == "年度审计"


def test_classify_uses_taxonomy_classifier_and_schedules_topic_tree_update(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "audit-plan.pdf", "file_type": ".pdf"},
    )
    monkeypatch.setattr(
        classification_service_module,
        "get_document_content_record",
        lambda document_id: {"full_content": "候选人录用审批，需要确认薪资包、职级、offer和入职日期。"},
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: False)

    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )

    class FakeTaxonomyClassifier:
        async def classify(self, document_id, content, filename="", file_type=""):
            assert document_id == "doc-1"
            assert filename == "audit-plan.pdf"
            assert file_type == ".pdf"
            assert content.startswith("候选人录用审批")
            return {
                "classification_id": "hr.offer_approval",
                "classification_label": "Offer审批",
                "classification_path": ["人力资源", "招聘管理", "Offer审批"],
                "classification_score": 0.93,
                "classification_source": "llm",
                "classification_candidates": ["hr.offer_approval", "hr.recruitment"],
            }

    monkeypatch.setattr(classification_service_module, "TaxonomyClassifier", FakeTaxonomyClassifier)

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return Mock()

    monkeypatch.setattr(classification_service_module.asyncio, "create_task", fake_create_task)

    service = ClassificationService()
    service.topic_tree_service = Mock(classify_document=Mock())

    async def async_case():
        return service.classify("doc-1")

    payload = asyncio.run(async_case())

    assert payload["document_id"] == "doc-1"
    assert payload["filename"] == "audit-plan.pdf"
    assert payload["categories"] == ["人力资源", "招聘管理", "Offer审批"]
    assert payload["suggested_folders"] == ["人力资源/招聘管理/Offer审批"]
    assert payload["topic_id"] == "hr.offer_approval"
    assert payload["topic_label"] == "Offer审批"
    assert payload["confidence"] == 0.93
    assert payload["classification_source"] == "llm"
    assert updates[0][1]["classification_result"] == "Offer审批"
    assert updates[0][1]["classification_id"] == "hr.offer_approval"
    assert json.loads(updates[0][1]["classification_path"]) == ["人力资源", "招聘管理", "Offer审批"]
    assert updates[0][1]["classification_score"] == 0.93
    assert updates[0][1]["classification_source"] == "llm"
    assert json.loads(updates[0][1]["classification_candidates"]) == ["hr.offer_approval", "hr.recruitment"]
    assert len(scheduled) == 1
    scheduled[0].close()
    service.topic_tree_service.classify_document.assert_not_called()


def test_reclassify_uses_taxonomy_classifier_and_returns_old_new_labels(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "audit-plan.pdf",
            "file_type": ".pdf",
            "classification_result": "旧分类",
        },
    )
    monkeypatch.setattr(
        classification_service_module,
        "get_document_content_record",
        lambda document_id: {"full_content": "候选人录用审批，需要确认薪资包、职级、offer和入职日期。"},
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: False)

    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )

    class FakeTaxonomyClassifier:
        async def classify(self, document_id, content, filename="", file_type=""):
            return {
                "classification_id": "hr.offer_approval",
                "classification_label": "Offer审批",
                "classification_path": ["人力资源", "招聘管理", "Offer审批"],
                "classification_score": 0.88,
                "classification_source": "keyword",
                "classification_candidates": ["hr.offer_approval", "hr.recruitment"],
            }

    monkeypatch.setattr(classification_service_module, "TaxonomyClassifier", FakeTaxonomyClassifier)

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return Mock()

    monkeypatch.setattr(classification_service_module.asyncio, "create_task", fake_create_task)

    service = ClassificationService()
    service.topic_tree_service = Mock(classify_document=Mock())

    async def async_case():
        return service.reclassify("doc-1")

    payload = asyncio.run(async_case())

    assert payload["old_classification"] == "旧分类"
    assert payload["new_classification"] == "Offer审批"
    assert payload["categories"] == ["人力资源", "招聘管理", "Offer审批"]
    assert payload["topic_id"] == "hr.offer_approval"
    assert payload["classification_source"] == "keyword"
    assert updates[0][1]["classification_result"] == "Offer审批"
    assert updates[0][1]["classification_id"] == "hr.offer_approval"
    assert json.loads(updates[0][1]["classification_path"]) == ["人力资源", "招聘管理", "Offer审批"]
    assert updates[0][1]["classification_score"] == 0.88
    assert updates[0][1]["classification_source"] == "keyword"
    assert json.loads(updates[0][1]["classification_candidates"]) == ["hr.offer_approval", "hr.recruitment"]
    assert len(scheduled) == 1
    scheduled[0].close()
    service.topic_tree_service.classify_document.assert_not_called()


def test_classify_document_payload_field_is_absent_uses_preview_content_and_full_content(monkeypatch):
    updates = []

    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "labor-contract.docx",
            "preview_content": "",
            "full_content": "本协议约定劳动期限、薪酬与保密义务。",
        },
    )
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: {})

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "labor-contract.docx"
            assert text == "本协议约定劳动期限、薪酬与保密义务。"
            return "劳动合同"

        async def arbitrate_labels(self, text, label_a, label_b):
            raise AssertionError("arbitrate_labels should not be called when label_a is missing")

    monkeypatch.setattr(llm_gateway_module, "LLMGateway", FakeGateway)

    service = ClassificationService()
    service.topic_tree_service = Mock(
        classify_document=Mock(
            return_value={
                "document_id": "doc-2",
                "topic_id": "topic-fallback-1",
                "topic_label": "",
                "topic_path": [],
                "confidence": 1.0,
            }
        )
    )

    label = asyncio.run(service.classify_document("doc-2"))

    assert label == "劳动合同"
    assert any(
        document_id == "doc-2" and payload.get("classification_result") == "劳动合同"
        for document_id, payload in updates
    )


def test_classify_document_processing_failures_returns_error_without_invoking_llm(monkeypatch):
    updates = []

    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "broken.docx",
            "preview_content": "Word处理失败: Package not found at '/tmp/broken.docx'",
            "full_content": "",
        },
    )
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: None)

    class ForbiddenGateway:
        def __init__(self, *args, **kwargs):
            raise AssertionError("LLMGateway should not be created for parser failure text")

    monkeypatch.setattr(llm_gateway_module, "LLMGateway", ForbiddenGateway)

    service = ClassificationService()
    service.topic_tree_service = Mock(classify_document=Mock(return_value={"topic_label": "年度审计"}))

    label = asyncio.run(service.classify_document("doc-3"))

    assert label == "Error"
    service.topic_tree_service.classify_document.assert_not_called()
    assert any(
        document_id == "doc-3" and payload.get("classification_result") == "Error"
        for document_id, payload in updates
    )


def test_get_document_multi_level_info_error_doc_exposes_topic_tree_fallback_contract(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "broken.docx"},
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: True)

    service = ClassificationService()
    payload = service.get_document_multi_level_info("doc-error")

    assert payload["categories"] == ["异常文档", "Error"]
    assert payload["topic_path"] == ["异常文档", "Error"]
    assert payload["suggested_folders"] == ["异常文档/Error"]


def test_classify_error_document_persist_clears_stale_topic_metadata(monkeypatch):
    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "broken.docx"},
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )

    service = ClassificationService()
    payload = service.classify("doc-error")

    assert payload["topic_path"] == ["异常文档", "Error"]
    assert len(updates) == 1
    _, persisted = updates[0]
    assert persisted["classification_result"] == "Error"
    assert persisted["classification_confidence"] == 1.0
    assert persisted["classification_method"] == "content_error_fallback"
    assert persisted["topic_node_id"] is None
    assert persisted["topic_label"] is None
    assert persisted["topic_path"] == []
    assert persisted["topic_parent_label"] is None
    assert persisted["topic_tree_generated_at"] is None


def test_classify_document_fallback_topic_tree_label_is_persisted(monkeypatch):
    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "labor-contract.docx",
            "preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。",
        },
    )
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )

    async def explode_resolver(*args, **kwargs):
        raise RuntimeError("resolver failed")

    monkeypatch.setattr(classification_service_module, "resolve_document_label", explode_resolver)

    service = ClassificationService()
    service.topic_tree_service = Mock(
        classify_document=Mock(
            return_value={
                "document_id": "doc-4",
                "topic_id": "topic-1",
                "topic_label": "年度审计",
                "topic_path": ["财务治理", "年度审计"],
                "confidence": 1.0,
            }
        )
    )

    label = asyncio.run(service.classify_document("doc-4"))

    assert label == "年度审计"
    service.topic_tree_service.classify_document.assert_called_once_with("doc-4", force_rebuild=False)
    assert any(
        document_id == "doc-4"
        and payload.get("classification_result") == "年度审计"
        and payload.get("classification_method") == "topic_tree_fallback"
        for document_id, payload in updates
    )


def test_classify_document_treats_normalized_error_label_from_resolver_as_error(monkeypatch):
    updates = []
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "Error.docx",
            "preview_content": "这是一段可用内容",
        },
    )
    monkeypatch.setattr(
        classification_service_module,
        "update_document_info",
        lambda document_id, updated_info: updates.append((document_id, updated_info)) or True,
    )
    monkeypatch.setattr(classification_service_module, "is_error_document", lambda *args, **kwargs: False)

    async def resolver_returns_error_label(*args, **kwargs):
        return {"label": "Error", "is_error": False, "source_text": "这是一段可用内容", "source": "heuristic"}

    monkeypatch.setattr(classification_service_module, "resolve_document_label", resolver_returns_error_label)

    class FakeGateway:
        async def arbitrate_labels(self, text, label_a, label_b):
            raise AssertionError("should not arbitrate when resolver returns Error label")

    monkeypatch.setattr(llm_gateway_module, "LLMGateway", FakeGateway)

    service = ClassificationService()
    service.topic_tree_service = Mock(
        classify_document=Mock(
            return_value={
                "document_id": "doc-11",
                "topic_id": "topic-1",
                "topic_label": "年度审计",
                "topic_path": ["财务治理", "年度审计"],
                "confidence": 1.0,
            }
        )
    )

    label = asyncio.run(service.classify_document("doc-11"))

    assert label == "Error"
    assert any(
        document_id == "doc-11"
        and payload.get("classification_result") == "Error"
        and payload.get("classification_method") == "content_error_fallback"
        for document_id, payload in updates
    )


def test_categories_api_returns_topic_tree_backed_payload(monkeypatch):
    mock_get_categories = Mock(
        return_value=[
            {
                "id": "hr.offer_approval",
                "label": "Offer审批",
                "path": ["人力资源", "招聘管理", "Offer审批"],
                "domain": "人力资源",
            }
        ]
    )
    monkeypatch.setattr(classification_api.classification_service, "get_categories", mock_get_categories)

    body = asyncio.run(classification_api.get_all_categories())

    assert body["code"] == 200
    assert body["data"][0]["id"] == "hr.offer_approval"
    mock_get_categories.assert_called_once()


def test_unclassified_excluded_document_should_expose_fallback_topic_contract(monkeypatch):
    documents = {
        "doc-1": {
            "id": "doc-1",
            "filename": "audit-plan.pdf",
            "file_type": ".pdf",
            "classification_result": "年度审计",
            "created_at_iso": "2026-04-01T10:00:00",
        },
        "doc-2": {
            "id": "doc-2",
            "filename": "labor-contract.docx",
            "file_type": ".docx",
            "classification_result": None,
            "created_at_iso": "2026-04-02T10:00:00",
        },
    }

    class FakeStore:
        def __init__(self):
            self.saved = None

        def save_artifact(self, name, payload):
            self.saved = (name, payload)
            return True

        def load_artifact(self, name):
            return None

    class FakeTopicClusteringWithExcluded:
        def __init__(self, *args, **kwargs):
            pass

        def build_document_vectors(self, docs):
            return (
                [{**docs[0], "vector": [1.0, 0.0]}],
                [{**docs[1], "exclude_reason": "missing_vector"}],
            )

        def cluster_documents(self, docs, level):
            return [{"documents": docs, "representatives": docs[:1], "center": [1.0, 0.0]}]

    class FakeTopicLabeler:
        def label_parent_topic(self, representatives):
            return {"label": "财务治理", "summary": "围绕审计与整改治理"}

        def label_child_topic(self, parent_label, representatives):
            return {"label": "年度审计", "summary": "围绕年度审计计划与报告"}

    fake_store = FakeStore()
    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", lambda: [documents["doc-1"], documents["doc-2"]])
    monkeypatch.setattr(
        topic_tree_service_module,
        "get_document_content_record",
        lambda document_id: {
            "doc-1": {"preview_content": "年度审计计划与整改安排"},
            "doc-2": {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
        }[document_id],
    )
    monkeypatch.setattr(topic_tree_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: True)
    monkeypatch.setattr(topic_tree_service_module, "get_metadata_store", lambda data_dir=None: fake_store)
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "TopicLabeler", FakeTopicLabeler, raising=False)
    def resolve_document_label(document_id, doc_info):
        if document_id == "doc-2":
            return {
                "label": "劳动合同",
                "source_text": (doc_info or {}).get("preview_content", ""),
                "is_error": False,
                "source": "test_stub",
            }
        return {
            "label": None,
            "source_text": (doc_info or {}).get("preview_content", ""),
            "is_error": False,
            "source": "test_stub",
        }

    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", resolve_document_label, raising=False)

    monkeypatch.setattr(classification_service_module, "get_document_info", lambda document_id: documents.get(document_id))
    monkeypatch.setattr(
        classification_service_module,
        "get_document_content_record",
        lambda document_id: {
            "doc-1": {"preview_content": "年度审计计划与整改安排"},
            "doc-2": {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
        }.get(document_id, {}),
    )

    service = ClassificationService()
    payload = service.get_document_multi_level_info("doc-2")

    assert fake_store.saved is not None
    assert payload["topic_label"] == "劳动合同"
    assert payload["topic_path"] == ["兜底分类", "劳动合同"]
    assert payload["categories"] == ["兜底分类", "劳动合同"]
