import asyncio
import os
import sys

from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.classification as classification_api  # noqa: E402
import app.services.classification_service as classification_service_module  # noqa: E402
from app.services.classification_service import ClassificationService  # noqa: E402


def _topic_tree_payload():
    return {
        "schema_version": 2,
        "generated_at": "2026-04-16T10:00:00",
        "total_documents": 3,
        "clustered_documents": 3,
        "excluded_documents": 0,
        "topic_count": 1,
        "generation_method": "doc_embedding_cluster+llm_label",
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


def test_get_categories_comes_from_topic_tree_leaf_nodes(monkeypatch):
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


def test_classify_uses_topic_tree_assignment_instead_of_legacy_classifier(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "audit-plan.pdf"},
    )

    service = ClassificationService()
    service.topic_tree_service = Mock(
        classify_document=Mock(
            return_value={
                "document_id": "doc-1",
                "topic_id": "topic-1-1",
                "topic_label": "年度审计",
                "topic_path": ["财务治理", "年度审计"],
                "confidence": 1.0,
            }
        )
    )

    payload = service.classify("doc-1")

    assert payload["document_id"] == "doc-1"
    assert payload["filename"] == "audit-plan.pdf"
    assert payload["categories"] == ["财务治理", "年度审计"]
    assert payload["suggested_folders"] == ["财务治理/年度审计"]
    assert payload["topic_id"] == "topic-1-1"
    assert payload["topic_label"] == "年度审计"
    service.topic_tree_service.classify_document.assert_called_once_with("doc-1", force_rebuild=True)


def test_reclassify_uses_topic_tree_assignment_and_returns_compatibility_fields(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "audit-plan.pdf",
            "classification_result": "旧分类",
        },
    )

    service = ClassificationService()
    service.topic_tree_service = Mock(
        classify_document=Mock(
            return_value={
                "document_id": "doc-1",
                "topic_id": "topic-1-1",
                "topic_label": "年度审计",
                "topic_path": ["财务治理", "年度审计"],
                "confidence": 1.0,
            }
        )
    )

    payload = service.reclassify("doc-1")

    assert payload["old_classification"] == "旧分类"
    assert payload["new_classification"] == "年度审计"
    assert payload["categories"] == ["财务治理", "年度审计"]
    assert payload["topic_id"] == "topic-1-1"
    service.topic_tree_service.classify_document.assert_called_once_with("doc-1", force_rebuild=True)


def test_categories_api_returns_topic_tree_backed_payload(monkeypatch):
    mock_get_categories = Mock(
        return_value={
            "categories": ["年度审计", "供应商比价"],
            "document_count": {"年度审计": 2, "供应商比价": 1},
        }
    )
    monkeypatch.setattr(classification_api.classification_service, "get_categories", mock_get_categories)

    body = asyncio.run(classification_api.get_all_categories())

    assert body["code"] == 200
    assert body["data"]["categories"] == ["年度审计", "供应商比价"]
    mock_get_categories.assert_called_once()
