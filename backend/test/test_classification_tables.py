import os
import sys
import asyncio
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.classification as classification_api  # noqa: E402
import app.services.classification_service as classification_service_module  # noqa: E402
from app.services.classification_service import ClassificationService  # noqa: E402


def test_generate_classification_table_hydrates_results_and_persists(monkeypatch):
    captured = {}

    def fake_get_document_info(document_id):
        return {
            "id": document_id,
            "filename": "budget-report.pdf",
            "classification_result": "财务",
            "created_at_iso": "2026-03-20T10:00:00",
        }

    def fake_generate_classification_table(query, results):
        captured["query"] = query
        captured["results"] = results
        return {
            "query": query,
            "title": "预算相关资料分组",
            "summary": "按财务资料聚合",
            "rows": [
                {
                    "label": "财务",
                    "document_count": 1,
                    "keywords": ["预算", "审批"],
                }
            ],
        }

    save_mock = Mock(return_value="table-1")
    monkeypatch.setattr(classification_service_module, "get_document_info", fake_get_document_info)
    monkeypatch.setattr(classification_service_module, "generate_classification_table", fake_generate_classification_table)
    monkeypatch.setattr(classification_service_module, "save_classification_table_record", save_mock)

    service = ClassificationService()
    result = service.generate_classification_table(
        "预算",
        [
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "best_excerpt": "预算审批流程",
                "best_block_id": "doc-1#2",
                "evidence_blocks": [
                    {
                        "block_id": "doc-1#2",
                        "block_index": 2,
                        "snippet": "预算审批流程",
                        "score": 0.95,
                    }
                ],
            }
        ],
        persist=True,
    )

    assert captured["query"] == "预算"
    assert captured["results"][0]["classification_result"] == "财务"
    assert captured["results"][0]["created_at_iso"] == "2026-03-20T10:00:00"
    assert captured["results"][0]["best_excerpt"] == "预算审批流程"
    assert result["id"] == "table-1"
    save_mock.assert_called_once()


def test_generate_classification_table_api_returns_service_payload(monkeypatch):
    mock_generate = Mock(
        return_value={
            "id": "table-1",
            "query": "预算",
            "title": "预算相关资料分组",
            "summary": "按财务资料聚合",
            "rows": [],
        }
    )
    monkeypatch.setattr(classification_api.classification_service, "generate_classification_table", mock_generate)

    request_model = classification_api.ClassificationTableGenerateRequest(
        query="预算",
        results=[{"document_id": "doc-1"}],
        persist=True,
    )

    body = asyncio.run(classification_api.generate_classification_table(request_model))

    assert body["code"] == 200
    assert body["data"]["id"] == "table-1"
    mock_generate.assert_called_once_with("预算", [{"document_id": "doc-1"}], persist=True)


def test_classify_returns_topic_tree_assignment_payload(monkeypatch):
    monkeypatch.setattr(
        classification_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "guide.pdf",
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

    result = service.classify("doc-1")

    assert result["categories"] == ["财务治理", "年度审计"]
    assert result["topic_id"] == "topic-1-1"
    assert result["topic_label"] == "年度审计"
