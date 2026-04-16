import os
import sys
import asyncio
import json
import unittest
from unittest.mock import Mock
from unittest import mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.retrieval as retrieval_api  # noqa: E402
import app.services.retrieval_service as retrieval_service_module  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402
import utils.smart_retrieval as smart_retrieval_module  # noqa: E402
import utils.search_cache as search_cache_module  # noqa: E402

def test_workspace_search_groups_block_results_and_applies_filters(monkeypatch):
    captured = {}

    def fake_get_ready_block_document_ids(**kwargs):
        captured["ready_filters"] = kwargs
        return {"doc-1"}

    def fake_search_block_documents(**kwargs):
        captured["search"] = kwargs
        return {
            "documents": [
                {
                    "document_id": "doc-1",
                    "filename": "budget-report.pdf",
                    "path": "/docs/budget-report.pdf",
                    "file_type": ".pdf",
                    "classification_result": "财务",
                    "created_at_iso": "2026-03-20T10:00:00",
                    "parser_name": "pdf",
                    "extraction_status": "ready",
                    "preview_content": "预算审批流程和采购说明",
                    "file_available": True,
                    "score": 0.94,
                    "hit_count": 1,
                    "best_block_id": "doc-1:block-v1:0",
                    "evidence_blocks": [
                        {
                            "block_id": "doc-1:block-v1:0",
                            "block_index": 0,
                            "block_type": "paragraph",
                            "snippet": "预算审批流程和采购说明",
                            "heading_path": ["预算管理"],
                            "page_number": 1,
                            "score": 0.94,
                            "match_reason": "heading + body match",
                        }
                    ],
                }
            ],
            "results": [],
            "meta": {"fallback_used": False},
        }

    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", fake_get_ready_block_document_ids)
    monkeypatch.setattr(retrieval_service_module, "search_block_documents", fake_search_block_documents)

    service = RetrievalService()
    payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        retrieval_version="legacy",
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

    assert captured["ready_filters"] == {
        "file_types": ["pdf"],
        "filename": "budget",
        "classification": "财务",
        "date_from": "2026-03-01",
        "date_to": "2026-03-31",
    }
    assert captured["search"]["query"] == "预算"
    assert captured["search"]["mode"] == "hybrid"
    assert captured["search"]["limit"] == 5
    assert captured["search"]["alpha"] == 0.35
    assert captured["search"]["use_rerank"] is False
    assert captured["search"]["ready_document_ids"] == {"doc-1"}
    assert payload["total_results"] == 1
    assert payload["total_documents"] == 1
    assert payload["retrieval_version_requested"] == "block"
    assert payload["retrieval_version_used"] == "block"
    assert payload["results"][0]["document_id"] == "doc-1"
    assert payload["results"][0]["content_snippet"] == "预算审批流程和采购说明"
    assert payload["results"][0]["similarity"] == 0.94
    assert payload["documents"][0]["document_id"] == "doc-1"
    assert payload["documents"][0]["best_block_id"] == "doc-1:block-v1:0"
    assert payload["documents"][0]["preview_content"] == "预算审批流程和采购说明"
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


def test_workspace_search_returns_empty_block_payload_when_no_ready_docs(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    captured = {}

    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", lambda **kwargs: set())
    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy hybrid_search should not be used")),
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "search_block_documents",
        lambda **kwargs: captured.update(kwargs) or {"documents": [], "results": [], "meta": {"fallback_used": False}},
    )

    payload = RetrievalService().workspace_search(
        query="报销标准",
        mode="hybrid",
        retrieval_version="legacy",
        limit=10,
        group_by_document=True,
    )

    assert captured["ready_document_ids"] == set()
    assert payload["retrieval_version_requested"] == "block"
    assert payload["retrieval_version_used"] == "block"
    assert payload["total_documents"] == 0
    assert payload["total_results"] == 0
    assert payload["meta"]["fallback_used"] is False


async def _read_streaming_response(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def test_workspace_search_stream_rerank_updates_documents_payload(monkeypatch):
    hybrid_payload = {
        "query": "预算",
        "mode": "hybrid",
        "total_results": 2,
        "total_documents": 2,
        "results": [
            {
                "document_id": "doc-1",
                "filename": "budget-plan.pdf",
                "file_type": ".pdf",
                "similarity": 0.61,
                "content_snippet": "预算计划",
                "chunk_index": 0,
                "file_available": True,
            },
            {
                "document_id": "doc-2",
                "filename": "budget-report.pdf",
                "file_type": ".pdf",
                "similarity": 0.58,
                "content_snippet": "预算报告",
                "chunk_index": 0,
                "file_available": True,
            },
        ],
        "documents": [
            {"document_id": "doc-1", "filename": "budget-plan.pdf"},
            {"document_id": "doc-2", "filename": "budget-report.pdf"},
        ],
    }
    regrouped_payload = {
        **hybrid_payload,
        "mode": "smart",
        "results": [
            {**hybrid_payload["results"][1], "similarity": 0.95},
            {**hybrid_payload["results"][0], "similarity": 0.42},
        ],
        "documents": [
            {"document_id": "doc-2", "filename": "budget-report.pdf"},
            {"document_id": "doc-1", "filename": "budget-plan.pdf"},
        ],
        "total_results": 2,
        "total_documents": 2,
    }

    monkeypatch.setattr(retrieval_api.retrieval_service, "workspace_search", Mock(return_value=hybrid_payload))
    monkeypatch.setattr(retrieval_api, "is_llm_available", lambda: True)
    monkeypatch.setattr(
        retrieval_api,
        "llm_rerank",
        lambda query, results, top_k: [
            {**results[1], "similarity": 0.95},
            {**results[0], "similarity": 0.42},
        ],
    )
    monkeypatch.setattr(
        retrieval_api.retrieval_service,
        "regroup_workspace_payload",
        Mock(return_value=regrouped_payload),
        raising=False,
    )

    response = asyncio.run(
        retrieval_api.workspace_search_stream(
            retrieval_api.WorkspaceSearchRequest(
                query="预算",
                mode="smart",
                limit=2,
                group_by_document=True,
            )
        )
    )
    stream_text = asyncio.run(_read_streaming_response(response))

    reranked_frames = [
        frame for frame in stream_text.split("\n\n")
        if frame.startswith("event: reranked")
    ]
    assert len(reranked_frames) == 1
    reranked_payload = json.loads(reranked_frames[0].split("data: ", 1)[1])
    assert reranked_payload["documents"][0]["document_id"] == "doc-2"
    assert reranked_payload["results"][0]["document_id"] == "doc-2"


def test_workspace_search_block_mode_forwards_filename_filter(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    captured = {}

    def fake_get_ready_block_document_ids(**kwargs):
        captured.update(kwargs)
        return {"doc-1"}

    monkeypatch.setattr(retrieval_service_module, "get_ready_block_document_ids", fake_get_ready_block_document_ids)
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
                    "hit_count": 1,
                    "best_block_id": "doc-1:block-v1:14",
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
            "results": [],
            "meta": {"fallback_used": False},
        },
    )

    payload = RetrievalService().workspace_search(
        query="报销标准",
        mode="hybrid",
        retrieval_version="legacy",
        filename="财务制度",
        limit=10,
        group_by_document=True,
    )

    assert captured["filename"] == "财务制度"
    assert payload["retrieval_version_requested"] == "block"
    assert payload["retrieval_version_used"] == "block"
    assert payload["results"][0]["heading_path"] == ["第三章 财务管理", "3.2 报销标准"]


def test_workspace_search_stream_hybrid_phase_uses_block_payload(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    monkeypatch.setattr(
        retrieval_api.retrieval_service,
        "workspace_search",
        Mock(
            return_value={
                "query": "预算",
                "mode": "hybrid",
                "retrieval_version_requested": "block",
                "retrieval_version_used": "block",
                "total_results": 1,
                "total_documents": 1,
                "results": [
                    {
                        "document_id": "doc-1",
                        "filename": "budget-plan.pdf",
                        "file_type": ".pdf",
                        "block_id": "doc-1:block-v1:0",
                        "content_snippet": "预算计划",
                        "similarity": 0.88,
                    }
                ],
                "documents": [{"document_id": "doc-1", "filename": "budget-plan.pdf"}],
                "meta": {"fallback_used": False},
                "applied_filters": {},
            }
        ),
    )
    monkeypatch.setattr(retrieval_api, "is_llm_available", lambda: False)

    response = asyncio.run(
        retrieval_api.workspace_search_stream(
            retrieval_api.WorkspaceSearchRequest(query="预算", mode="smart", limit=2, group_by_document=True)
        )
    )
    stream_text = asyncio.run(_read_streaming_response(response))

    results_frames = [
        frame for frame in stream_text.split("\n\n")
        if frame.startswith("event: results")
    ]
    assert len(results_frames) == 1
    results_payload = json.loads(results_frames[0].split("data: ", 1)[1])
    assert results_payload["retrieval_version_requested"] == "block"
    assert results_payload["retrieval_version_used"] == "block"
    assert results_payload["results"][0]["block_id"] == "doc-1:block-v1:0"
    assert "event: reranked" not in stream_text


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


class DoubaoOnlyRetrievalTests(unittest.TestCase):
    def test_llm_status_reports_doubao_only_payload_and_default_model(self):
        with mock.patch.object(retrieval_service_module, "is_llm_available", return_value=True):
            with mock.patch.object(retrieval_service_module, "DOUBAO_API_KEY", "doubao-key"):
                with mock.patch.object(retrieval_service_module, "DOUBAO_DEFAULT_LLM_MODEL", "doubao-mini-for-test"):
                    payload = RetrievalService().llm_status()

        self.assertEqual(
            payload,
            {
                "llm_available": True,
                "provider": "doubao",
                "doubao_configured": True,
                "default_model": "doubao-mini-for-test",
            },
        )

    def test_call_llm_uses_default_doubao_model_in_request_payload(self):
        smart_retrieval_module._llm_client = None
        smart_retrieval_module._llm_provider = None

        fake_response = mock.Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                    }
                }
            ]
        }

        with mock.patch.object(smart_retrieval_module, "DOUBAO_API_KEY", "doubao-key"):
            with mock.patch.object(smart_retrieval_module, "DOUBAO_LLM_API_URL", "https://doubao.test/chat"):
                with mock.patch.object(smart_retrieval_module, "DOUBAO_DEFAULT_LLM_MODEL", "doubao-mini-for-test"):
                    with mock.patch.object(smart_retrieval_module.requests, "post", return_value=fake_response) as post_mock:
                        response_text = smart_retrieval_module._call_llm("hello", max_tokens=32, temperature=0.2)

        self.assertEqual(response_text, "ok")
        self.assertEqual(post_mock.call_args.kwargs["json"]["model"], "doubao-mini-for-test")
