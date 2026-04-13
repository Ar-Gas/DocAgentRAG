import os
import sys
import asyncio
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.retrieval as retrieval_api  # noqa: E402
import app.services.retrieval_service as retrieval_service_module  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402
import utils.search_cache as search_cache_module  # noqa: E402

def test_workspace_search_groups_results_and_applies_filters(monkeypatch):
    captured = {}

    def fake_hybrid_search(query, limit=10, alpha=0.5, use_rerank=True, file_types=None):
        captured["query"] = query
        captured["limit"] = limit
        captured["alpha"] = alpha
        captured["use_rerank"] = use_rerank
        captured["file_types"] = file_types
        return [
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "path": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.94,
                "content_snippet": "预算审批流程和采购说明",
                "chunk_index": 0,
            },
            {
                "document_id": "doc-2",
                "filename": "hr-notice.docx",
                "path": "/docs/hr-notice.docx",
                "file_type": ".docx",
                "similarity": 0.68,
                "content_snippet": "人事制度通知",
                "chunk_index": 1,
            },
        ]

    def fake_get_document_info(document_id):
        items = {
            "doc-1": {
                "id": "doc-1",
                "filename": "budget-report.pdf",
                "file_type": ".pdf",
                "classification_result": "财务",
                "created_at_iso": "2026-03-20T10:00:00",
                "parser_name": "pdf",
                "extraction_status": "ready",
                "preview_content": "预算审批流程和采购说明",
            },
            "doc-2": {
                "id": "doc-2",
                "filename": "hr-notice.docx",
                "file_type": ".docx",
                "classification_result": "人事",
                "created_at_iso": "2026-03-19T09:00:00",
                "parser_name": "word",
                "extraction_status": "ready",
                "preview_content": "人事制度通知",
            },
        }
        return items[document_id]

    def fake_get_document_content_record(document_id):
        return {
            "document_id": document_id,
            "preview_content": f"{document_id}-preview",
            "full_content": f"{document_id}-full",
        }

    def fake_list_document_segments(document_id):
        return [
            {
                "segment_id": f"{document_id}#0",
                "segment_index": 0,
                "content": f"{document_id} segment 0",
            },
            {
                "segment_id": f"{document_id}#1",
                "segment_index": 1,
                "content": f"{document_id} segment 1",
            },
        ]

    monkeypatch.setattr(retrieval_service_module, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(retrieval_service_module, "get_document_info", fake_get_document_info)
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", fake_get_document_content_record)
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", fake_list_document_segments)
    monkeypatch.setattr(retrieval_service_module, "get_all_documents", lambda: [])

    service = RetrievalService()
    payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        limit=5,
        alpha=0.35,
        use_rerank=False,
        file_types=["pdf"],
        filename="budget",
        classification="财务",
        date_from="2026-03-01",
        date_to="2026-03-31",
        group_by_document=True,
    )

    assert captured == {
        "query": "预算",
        "limit": 15,
        "alpha": 0.35,
        "use_rerank": False,
        "file_types": ["pdf"],
    }
    assert payload["total_results"] == 1
    assert payload["total_documents"] == 1
    assert payload["results"][0]["document_id"] == "doc-1"
    assert payload["results"][0]["classification_result"] == "财务"
    assert payload["documents"][0]["document_id"] == "doc-1"
    assert payload["documents"][0]["top_segments"][0]["segment_index"] == 0
    assert payload["documents"][0]["preview_content"] == "doc-1-preview"
    assert payload["applied_filters"]["classification"] == "财务"


def test_workspace_search_api_returns_service_payload(monkeypatch):
    mock_workspace_search = Mock(
        return_value={
            "query": "预算",
            "mode": "hybrid",
            "total_results": 1,
            "total_documents": 1,
            "results": [{"document_id": "doc-1"}],
            "documents": [{"document_id": "doc-1"}],
            "applied_filters": {},
        }
    )
    monkeypatch.setattr(retrieval_api.retrieval_service, "workspace_search", mock_workspace_search)

    request_model = retrieval_api.WorkspaceSearchRequest(
        query="预算",
        mode="hybrid",
        file_types=["pdf"],
        group_by_document=True,
    )

    body = asyncio.run(retrieval_api.workspace_search_api(request_model))

    assert body["code"] == 200
    assert body["data"]["total_documents"] == 1
    mock_workspace_search.assert_called_once()


def test_workspace_search_block_mode_returns_documents_and_compatibility_results(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    monkeypatch.setattr(
        retrieval_service_module,
        "search_block_documents",
        lambda **kwargs: {
            "documents": [
                {
                    "document_id": "doc-1",
                    "filename": "财务制度.docx",
                    "file_type": ".docx",
                    "score": 0.92,
                    "hit_count": 3,
                    "best_block_id": "doc-1:block-v1:14",
                    "classification_result": "财务制度",
                    "file_available": True,
                    "evidence_blocks": [
                        {
                            "block_id": "doc-1:block-v1:14",
                            "block_index": 14,
                            "block_type": "paragraph",
                            "snippet": "员工差旅报销标准如下……",
                            "heading_path": ["第三章 财务管理", "3.2 报销标准"],
                            "page_number": 12,
                            "score": 0.92,
                            "match_reason": "heading + body match",
                        }
                    ],
                }
            ],
            "results": [
                {
                    "document_id": "doc-1",
                    "block_id": "doc-1:block-v1:14",
                    "block_index": 14,
                    "snippet": "员工差旅报销标准如下……",
                    "score": 0.92,
                    "match_reason": "heading + body match",
                }
            ],
            "meta": {"fallback_used": False},
        },
    )
    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", lambda **kwargs: {"doc-1"})

    payload = RetrievalService().workspace_search(
        query="报销标准",
        mode="hybrid",
        retrieval_version="block",
        limit=10,
        group_by_document=True,
    )

    assert payload["retrieval_version_requested"] == "block"
    assert payload["retrieval_version_used"] == "block"
    assert payload["total_documents"] == 1
    assert payload["total_results"] == 1
    assert payload["results"][0]["block_id"] == "doc-1:block-v1:14"


def test_workspace_search_block_mode_falls_back_to_legacy_when_no_ready_docs(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", lambda **kwargs: set())
    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda **kwargs: [
            {
                "document_id": "doc-legacy",
                "filename": "legacy.pdf",
                "file_type": ".pdf",
                "similarity": 0.88,
                "content_snippet": "legacy snippet",
                "chunk_index": 0,
            }
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "legacy.pdf",
            "file_type": ".pdf",
            "created_at_iso": "2026-04-13T00:00:00",
        },
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_content_record",
        lambda document_id: {"preview_content": "legacy snippet"},
    )
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(retrieval_service_module, "get_all_documents", lambda: [])

    payload = RetrievalService().workspace_search(
        query="报销标准",
        mode="hybrid",
        retrieval_version="block",
        limit=10,
        group_by_document=True,
    )

    assert payload["retrieval_version_used"] == "legacy"
    assert payload["meta"]["fallback_used"] is True


def test_workspace_search_falls_back_to_metadata_when_index_is_empty(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    monkeypatch.setattr(retrieval_service_module, "hybrid_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-1",
                "filename": "budget-report.pdf",
                "filepath": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "preview_content": "预算审批流程和采购说明",
                "classification_result": "财务",
                "created_at_iso": "2026-03-20T10:00:00",
            }
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "budget-report.pdf",
            "filepath": "/docs/budget-report.pdf",
            "file_type": ".pdf",
            "preview_content": "预算审批流程和采购说明",
            "classification_result": "财务",
            "created_at_iso": "2026-03-20T10:00:00",
        },
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_content_record",
        lambda document_id: {
            "document_id": document_id,
            "preview_content": "预算审批流程和采购说明",
            "full_content": "预算审批流程和采购说明，包含预算执行、报销和采购节点。",
        },
    )
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])

    service = RetrievalService()

    payload = service.workspace_search(
        query="预算 审批",
        mode="hybrid",
        limit=5,
        group_by_document=True,
    )

    assert payload["total_results"] == 1
    assert payload["total_documents"] == 1
    assert payload["results"][0]["document_id"] == "doc-1"
    assert payload["results"][0]["filename"] == "budget-report.pdf"
    assert payload["results"][0]["similarity"] > 0


def test_workspace_search_returns_document_results_with_evidence(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda *args, **kwargs: [
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "path": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.92,
                "content_snippet": "预算审批流程和采购说明",
                "chunk_index": 2,
            },
            {
                "document_id": "doc-1",
                "filename": "budget-report.pdf",
                "path": "/docs/budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.81,
                "content_snippet": "预算执行和报销约束",
                "chunk_index": 5,
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "budget-report.pdf",
            "file_type": ".pdf",
            "classification_result": "财务制度",
            "created_at_iso": "2026-03-20T10:00:00",
        },
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_content_record",
        lambda document_id: {
            "document_id": document_id,
            "preview_content": "预算审批流程和采购说明",
        },
    )
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(retrieval_service_module, "get_all_documents", lambda: [])

    payload = RetrievalService().workspace_search(query="预算 审批", mode="hybrid", limit=10)

    assert payload["documents"][0]["document_id"] == "doc-1"
    assert payload["documents"][0]["hit_count"] == 2
    assert payload["documents"][0]["best_excerpt"] == "预算审批流程和采购说明"
    assert payload["documents"][0]["best_block_id"] == "doc-1#2"
    assert payload["documents"][0]["evidence_blocks"][0]["block_index"] == 2
    assert payload["documents"][0]["evidence_blocks"][1]["block_index"] == 5


def test_stats_include_document_and_index_counts(monkeypatch):
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_stats",
        lambda: {
            "total_chunks": 7,
            "vector_indexed_documents": 2,
            "file_types": {".pdf": 5, ".docx": 2},
        },
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {"id": "doc-1", "filename": "a.pdf"},
            {"id": "doc-2", "filename": "b.docx"},
            {"id": "doc-3", "filename": "c.txt"},
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_content_record",
        lambda document_id: {},
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "list_document_segments",
        lambda document_id: [{"segment_id": f"{document_id}#0"}] if document_id != "doc-3" else [],
    )

    service = RetrievalService()
    payload = service.stats()

    assert payload["total_documents"] == 3
    assert payload["vector_indexed_documents"] == 2
    assert payload["segment_documents"] == 2
    assert payload["total_chunks"] == 7
    assert payload["file_types"] == {".pdf": 5, ".docx": 2}
