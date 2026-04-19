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
