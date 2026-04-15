import os
import sys
import asyncio
import unittest
from unittest.mock import Mock
from unittest import mock

import pytest
from pydantic import ValidationError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.retrieval as retrieval_api  # noqa: E402
import api.dependencies as api_dependencies  # noqa: E402
import app.services.retrieval_service as retrieval_service_module  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402
import utils.smart_retrieval as smart_retrieval_module  # noqa: E402
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
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-1",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-budget",
            },
            {
                "id": "doc-2",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
                "business_category_id": "cat-hr",
            },
        ],
    )

    service = RetrievalService()
    payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        limit=5,
        alpha=0.35,
        use_rerank=False,
        file_types=["pdf"],
        filename="budget",
        date_from="2026-03-01",
        date_to="2026-03-31",
        group_by_document=True,
        visibility_scope="department",
        department_id="dept-fin",
        business_category_id="cat-budget",
        current_user={"id": "user-1", "role_code": "system_admin"},
    )

    assert captured == {
        "query": "预算",
        "limit": 45,
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
    assert payload["applied_filters"]["visibility_scope"] == "department"
    assert payload["applied_filters"]["department_id"] == "dept-fin"
    assert payload["applied_filters"]["business_category_id"] == "cat-budget"


def test_workspace_search_filters_hidden_documents_before_response_assembly(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    service = RetrievalService()

    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda **kwargs: [
            {
                "document_id": "doc-visible",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "similarity": 0.91,
                "content_snippet": "预算审批",
                "chunk_index": 0,
            },
            {
                "document_id": "doc-hidden",
                "filename": "salary.xlsx",
                "file_type": ".xlsx",
                "similarity": 0.89,
                "content_snippet": "薪酬保密",
                "chunk_index": 0,
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-visible",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-budget",
            },
            {
                "id": "doc-hidden",
                "filename": "salary.xlsx",
                "file_type": ".xlsx",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
                "business_category_id": "cat-salary",
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "budget.pdf" if document_id == "doc-visible" else "salary.xlsx",
            "file_type": ".pdf" if document_id == "doc-visible" else ".xlsx",
            "classification_result": "财务" if document_id == "doc-visible" else "人事",
            "created_at_iso": "2026-04-15T10:00:00",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin" if document_id == "doc-visible" else "dept-hr",
            "shared_department_ids": [],
            "business_category_id": "cat-budget" if document_id == "doc-visible" else "cat-salary",
        },
    )
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", lambda document_id: {})
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(list_visible_document_ids=lambda current_user, documents: {"doc-visible"}),
        raising=False,
    )

    payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert [item["document_id"] for item in payload["results"]] == ["doc-visible"]
    assert payload["total_documents"] == 1


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

    current_user = {"id": "user-1", "role_code": "employee"}
    body = asyncio.run(retrieval_api.workspace_search_api(request_model, current_user=current_user))

    assert body["code"] == 200
    assert body["data"]["total_documents"] == 1
    mock_workspace_search.assert_called_once_with(
        query="预算",
        mode="hybrid",
        limit=10,
        alpha=0.5,
        use_rerank=False,
        file_types=["pdf"],
        filename=None,
        date_from=None,
        date_to=None,
        group_by_document=True,
        visibility_scope=None,
        department_id=None,
        business_category_id=None,
        current_user=current_user,
    )


def test_workspace_search_request_rejects_removed_fields():
    with pytest.raises(ValidationError):
        retrieval_api.WorkspaceSearchRequest(
            query="预算",
            retrieval_version="legacy",
        )


def test_legacy_retrieval_routes_require_authenticated_user():
    route_dependencies = {}
    for route in retrieval_api.router.routes:
        if not hasattr(route, "dependant"):
            continue
        route_dependencies[route.path] = {
            dependency.call for dependency in route.dependant.dependencies
        }

    for path in [
        "/search",
        "/hybrid-search",
        "/batch-search",
        "/document/{document_id}",
        "/stats",
        "/keyword-search",
        "/search-with-highlight",
        ]:
        assert api_dependencies.require_authenticated_user in route_dependencies[path]


def test_search_with_highlight_falls_back_to_hybrid_for_removed_smart_type(monkeypatch):
    captured = {}

    def fake_search_highlight(query, search_type, limit, alpha, use_rerank, file_types, current_user=None):
        captured["query"] = query
        captured["search_type"] = search_type
        return {
            "query": query,
            "search_type": search_type,
            "total": 0,
            "results": [],
        }

    monkeypatch.setattr(retrieval_api.retrieval_service, "search_highlight", fake_search_highlight)

    body = asyncio.run(
        retrieval_api.search_with_highlight_api(
            retrieval_api.SearchWithHighlightRequest(query="预算", search_type="smart"),
            current_user={"id": "user-1", "role_code": "employee"},
        )
    )

    assert body["code"] == 200
    assert captured["query"] == "预算"
    assert captured["search_type"] == "hybrid"


def test_search_types_omit_removed_smart_mode():
    body = asyncio.run(retrieval_api.get_search_types())

    assert body["code"] == 200
    assert [item["type"] for item in body["data"]["search_types"]] == ["keyword", "vector", "hybrid"]


def test_search_filters_hidden_documents_for_current_user(monkeypatch):
    service = RetrievalService()
    monkeypatch.setattr(
        retrieval_service_module,
        "search_documents",
        lambda *args, **kwargs: [
            {"document_id": "doc-visible", "filename": "budget.pdf"},
            {"document_id": "doc-hidden", "filename": "salary.xlsx"},
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-visible",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
            },
            {
                "id": "doc-hidden",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
            },
        ],
    )
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(list_visible_document_ids=lambda current_user, documents: {"doc-visible"}),
        raising=False,
    )

    payload = service.search(
        "预算",
        limit=10,
        use_rerank=False,
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert payload["total"] == 1
    assert [item["document_id"] for item in payload["results"]] == ["doc-visible"]


def test_search_backfills_visible_results_past_hidden_page_budget(monkeypatch):
    service = RetrievalService()
    requested_limits = []

    def fake_search_documents(query, limit=10, use_rerank=False, file_types=None):
        requested_limits.append(limit)
        return [
            {"document_id": "doc-hidden", "filename": "salary.xlsx"},
            {"document_id": "doc-visible", "filename": "budget.pdf"},
        ]

    monkeypatch.setattr(retrieval_service_module, "search_documents", fake_search_documents)
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-visible",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
            },
            {
                "id": "doc-hidden",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
            },
        ],
    )
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(list_visible_document_ids=lambda current_user, documents: {"doc-visible"}),
        raising=False,
    )

    payload = service.search(
        "预算",
        limit=1,
        use_rerank=False,
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert payload["total"] == 1
    assert [item["document_id"] for item in payload["results"]] == ["doc-visible"]
    assert requested_limits == [50]


def test_get_document_chunks_rejects_hidden_document(monkeypatch):
    service = RetrievalService()
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "visibility_scope": "department",
            "owner_department_id": "dept-hr",
            "shared_department_ids": [],
        },
    )
    monkeypatch.setattr(
        service.authorization_service,
        "can_view_document",
        lambda current_user, document: False,
    )

    with unittest.TestCase().assertRaises(retrieval_service_module.AppServiceError):
        service.get_document_chunks(
            "doc-hidden",
            current_user={"id": "user-1", "role_code": "employee"},
        )


def test_workspace_search_cache_key_includes_department_context(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    service = RetrievalService()
    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda **kwargs: [
            {
                "document_id": "doc-fin",
                "filename": "finance.pdf",
                "file_type": ".pdf",
                "similarity": 0.95,
                "content_snippet": "财务预算",
                "chunk_index": 0,
            },
            {
                "document_id": "doc-hr",
                "filename": "hr.pdf",
                "file_type": ".pdf",
                "similarity": 0.94,
                "content_snippet": "人事预算",
                "chunk_index": 0,
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-fin",
                "filename": "finance.pdf",
                "file_type": ".pdf",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
            },
            {
                "id": "doc-hr",
                "filename": "hr.pdf",
                "file_type": ".pdf",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "finance.pdf" if document_id == "doc-fin" else "hr.pdf",
            "file_type": ".pdf",
            "created_at_iso": "2026-04-15T10:00:00",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin" if document_id == "doc-fin" else "dept-hr",
            "shared_department_ids": [],
        },
    )
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", lambda document_id: {})
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(
            list_visible_document_ids=lambda current_user, documents: (
                {"doc-fin"} if current_user.get("department_id") == "dept-fin" else {"doc-hr"}
            )
        ),
        raising=False,
    )

    finance_payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        current_user={"id": "user-1", "role_code": "employee", "department_id": "dept-fin"},
    )
    hr_payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        current_user={"id": "user-1", "role_code": "employee", "department_id": "dept-hr"},
    )

    assert [item["document_id"] for item in finance_payload["results"]] == ["doc-fin"]
    assert [item["document_id"] for item in hr_payload["results"]] == ["doc-hr"]


def test_workspace_search_metadata_fallback_count_excludes_hidden_documents(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    service = RetrievalService()
    monkeypatch.setattr(service, "_run_workspace_query_search", lambda **kwargs: ([], {}))
    monkeypatch.setattr(
        service,
        "_search_workspace_metadata",
        lambda **kwargs: [
            {
                "document_id": "doc-visible",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "similarity": 0.91,
                "content_snippet": "预算审批",
                "chunk_index": 0,
            },
            {
                "document_id": "doc-hidden",
                "filename": "salary.xlsx",
                "file_type": ".xlsx",
                "similarity": 0.89,
                "content_snippet": "薪酬保密",
                "chunk_index": 0,
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-visible",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
            },
            {
                "id": "doc-hidden",
                "filename": "salary.xlsx",
                "file_type": ".xlsx",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "budget.pdf" if document_id == "doc-visible" else "salary.xlsx",
            "file_type": ".pdf" if document_id == "doc-visible" else ".xlsx",
            "created_at_iso": "2026-04-15T10:00:00",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin" if document_id == "doc-visible" else "dept-hr",
            "shared_department_ids": [],
        },
    )
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", lambda document_id: {})
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(list_visible_document_ids=lambda current_user, documents: {"doc-visible"}),
        raising=False,
    )

    payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert payload["meta"]["metadata_fallback_used"] is True
    assert payload["meta"]["metadata_fallback_count"] == 1


def test_workspace_search_metadata_fallback_count_respects_governance_filters(monkeypatch):
    search_cache_module.get_search_cache().invalidate_all()
    service = RetrievalService()
    monkeypatch.setattr(service, "_run_workspace_query_search", lambda **kwargs: ([], {}))
    monkeypatch.setattr(
        service,
        "_search_workspace_metadata",
        lambda **kwargs: [
            {
                "document_id": "doc-target",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "similarity": 0.91,
                "content_snippet": "预算审批",
                "chunk_index": 0,
            },
            {
                "document_id": "doc-other-category",
                "filename": "procurement.pdf",
                "file_type": ".pdf",
                "similarity": 0.89,
                "content_snippet": "采购立项",
                "chunk_index": 0,
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-target",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-budget",
            },
            {
                "id": "doc-other-category",
                "filename": "procurement.pdf",
                "file_type": ".pdf",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-procurement",
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "budget.pdf" if document_id == "doc-target" else "procurement.pdf",
            "file_type": ".pdf",
            "created_at_iso": "2026-04-15T10:00:00",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin",
            "shared_department_ids": [],
            "business_category_id": "cat-budget" if document_id == "doc-target" else "cat-procurement",
        },
    )
    monkeypatch.setattr(retrieval_service_module, "get_document_content_record", lambda document_id: {})
    monkeypatch.setattr(retrieval_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(
            list_visible_document_ids=lambda current_user, documents: {
                str(doc.get("id"))
                for doc in documents
                if doc.get("id")
            }
        ),
        raising=False,
    )

    payload = service.workspace_search(
        query="预算",
        mode="hybrid",
        business_category_id="cat-budget",
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert payload["meta"]["metadata_fallback_used"] is True
    assert payload["meta"]["metadata_fallback_count"] == 1
    assert [item["document_id"] for item in payload["results"]] == ["doc-target"]


def test_smart_search_total_candidates_excludes_hidden_documents(monkeypatch):
    service = RetrievalService()
    monkeypatch.setattr(
        retrieval_service_module,
        "hybrid_search",
        lambda **kwargs: [
            {
                "document_id": "doc-hidden",
                "filename": "salary.xlsx",
                "file_type": ".xlsx",
                "similarity": 0.98,
                "content_snippet": "薪酬保密",
                "chunk_index": 0,
            },
            {
                "document_id": "doc-visible",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "similarity": 0.92,
                "content_snippet": "预算审批",
                "chunk_index": 0,
            },
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-visible",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
            },
            {
                "id": "doc-hidden",
                "visibility_scope": "department",
                "owner_department_id": "dept-hr",
                "shared_department_ids": [],
            },
        ],
    )
    monkeypatch.setattr(
        service,
        "authorization_service",
        Mock(list_visible_document_ids=lambda current_user, documents: {"doc-visible"}),
        raising=False,
    )
    monkeypatch.setattr(smart_retrieval_module, "is_llm_available", lambda: False)

    payload = service.smart(
        query="预算",
        limit=1,
        use_query_expansion=False,
        use_llm_rerank=False,
        expansion_method="keyword",
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert payload["total"] == 1
    assert payload["meta"]["total_candidates"] == 1
    assert [item["document_id"] for item in payload["results"]] == ["doc-visible"]


def test_smart_multimodal_retrieval_uses_search_func_for_candidates(monkeypatch):
    monkeypatch.setattr(smart_retrieval_module, "is_llm_available", lambda: False)

    captured = {}

    def search_func(query, limit=10):
        captured["query"] = query
        captured["limit"] = limit
        return [
            {
                "document_id": "doc-visible",
                "filename": "budget.pdf",
                "file_type": ".pdf",
                "similarity": 0.92,
                "content_snippet": "预算审批",
                "chunk_index": 0,
            }
        ]

    results, meta = smart_retrieval_module.smart_multimodal_retrieval(
        query="预算",
        search_func=search_func,
        limit=2,
        image_url="https://example.com/demo.png",
        use_query_expansion=False,
        use_llm_rerank=False,
        expansion_method="keyword",
    )

    assert captured == {"query": "预算", "limit": 4}
    assert meta["total_candidates"] == 1
    assert [item["document_id"] for item in results] == ["doc-visible"]


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
        current_user={"id": "user-1", "role_code": "system_admin"},
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
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-1",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-budget",
            }
        ],
    )

    payload = RetrievalService().workspace_search(
        query="预算 审批",
        mode="hybrid",
        limit=10,
        current_user={"id": "user-1", "role_code": "system_admin"},
    )

    assert payload["documents"][0]["document_id"] == "doc-1"
    assert payload["documents"][0]["hit_count"] == 2
    assert payload["documents"][0]["best_excerpt"] == "预算审批流程和采购说明"
    assert payload["documents"][0]["best_block_id"] == "doc-1#2"
    assert payload["documents"][0]["evidence_blocks"][0]["block_index"] == 2
    assert payload["documents"][0]["evidence_blocks"][1]["block_index"] == 5


def test_stats_include_document_and_index_counts(monkeypatch):
    monkeypatch.setattr(
        retrieval_service_module,
        "get_all_documents",
        lambda: [
            {"id": "doc-1", "filename": "a.pdf", "file_type": ".pdf"},
            {"id": "doc-2", "filename": "b.docx", "file_type": ".docx"},
            {"id": "doc-3", "filename": "c.txt", "file_type": ".txt"},
        ],
    )
    monkeypatch.setattr(
        retrieval_service_module,
        "get_document_by_id",
        lambda document_id: (
            {"chunks": ["chunk-a", "chunk-b", "chunk-c"]}
            if document_id == "doc-1"
            else {"chunks": ["chunk-d", "chunk-e", "chunk-f", "chunk-g"]}
            if document_id == "doc-2"
            else None
        ),
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
    payload = service.stats(current_user={"id": "user-1", "role_code": "system_admin"})

    assert payload["total_documents"] == 3
    assert payload["vector_indexed_documents"] == 2
    assert payload["segment_documents"] == 2
    assert payload["total_chunks"] == 7
    assert payload["file_types"] == {".pdf": 1, ".docx": 1, ".txt": 1}


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
