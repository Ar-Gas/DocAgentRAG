import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.document as document_api  # noqa: E402


def test_document_list_exposes_taxonomy_fields_for_frontend():
    mock_list_documents = Mock(
        return_value={
            "items": [
                {
                    "id": "doc-1",
                    "filename": "offer.docx",
                    "filepath": "/repo/backend/classified_docs/人力资源/招聘管理/Offer审批/offer.docx",
                    "file_type": ".docx",
                    "created_at_iso": "2026-04-18T18:00:00",
                    "classification_result": "Offer审批",
                    "classification_id": "hr.offer_approval",
                    "classification_path": ["人力资源", "招聘管理", "Offer审批"],
                    "classification_score": 0.91,
                    "classification_source": "llm",
                    "ingest_status": "ready",
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        }
    )
    document_api.document_service.list_documents = mock_list_documents

    payload = asyncio.run(document_api.get_document_list(page=1, page_size=10))

    item = payload["data"]["items"][0]

    assert item["classification_id"] == "hr.offer_approval"
    assert item["classification_path"] == ["人力资源", "招聘管理", "Offer审批"]
    assert item["classification_score"] == 0.91
    assert item["classification_source"] == "llm"
    assert item["filepath"] == "/repo/backend/classified_docs/人力资源/招聘管理/Offer审批/offer.docx"
    assert item["path"] == "/repo/backend/classified_docs/人力资源/招聘管理/Offer审批/offer.docx"
    assert item["storage_path"] == "/repo/backend/classified_docs/人力资源/招聘管理/Offer审批/offer.docx"


def test_document_list_exposes_taxonomy_v3_metadata_for_frontend():
    mock_list_documents = Mock(
        return_value={
            "items": [
                {
                    "id": "doc-rust",
                    "filename": "Rust编程.pdf",
                    "file_type": ".pdf",
                    "classification_result": "编程语言书籍",
                    "classification_id": "books.computer.programming_language",
                    "classification_leaf_id": "books.computer.programming_language",
                    "classification_path": ["图书资料", "计算机图书", "编程语言书籍"],
                    "classification_domain": "图书资料",
                    "classification_score": 0.91,
                    "classification_confidence": 0.91,
                    "classification_source": "llm_hierarchical",
                    "classification_issue_code": None,
                    "taxonomy_version": "taxonomy_v3",
                    "ingest_status": "ready",
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        }
    )
    document_api.document_service.list_documents = mock_list_documents

    payload = asyncio.run(document_api.get_document_list(page=1, page_size=10))

    item = payload["data"]["items"][0]

    assert item["classification_leaf_id"] == "books.computer.programming_language"
    assert item["classification_domain"] == "图书资料"
    assert item["classification_confidence"] == 0.91
    assert item["classification_issue_code"] is None
    assert item["taxonomy_version"] == "taxonomy_v3"
