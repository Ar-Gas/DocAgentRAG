import asyncio
import io
import os
import sys
from pathlib import Path
from unittest.mock import Mock

from fastapi import UploadFile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.document as document_api  # noqa: E402
import app.services.document_service as document_service_module  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402
from app.services.errors import AppServiceError  # noqa: E402


def test_document_list_forwards_current_user_and_returns_governed_fields(monkeypatch):
    current_user = {"id": "user-1", "role_code": "employee", "department_ids": ["dept-fin"]}
    mock_list_documents = Mock(
        return_value={
            "items": [
                {
                    "id": "doc-1",
                    "filename": "budget.pdf",
                    "file_type": ".pdf",
                    "preview_content": "budget",
                    "full_content_length": 6,
                    "created_at_iso": "2026-04-15T00:00:00",
                    "classification_result": "finance",
                    "file_available": True,
                    "extraction_status": "ready",
                    "parser_name": "pdf",
                    "visibility_scope": "department",
                    "owner_department_id": "dept-fin",
                    "shared_department_ids": ["dept-ops"],
                    "business_category_id": "cat-budget",
                    "role_restriction": "employee",
                    "is_public_restricted": True,
                    "confidentiality_level": "confidential",
                    "document_status": "published",
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        }
    )
    monkeypatch.setattr(document_api.document_service, "list_documents", mock_list_documents)

    body = asyncio.run(
        document_api.get_document_list(
            page=1,
            page_size=10,
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    item = body["data"]["items"][0]
    assert item["visibility_scope"] == "department"
    assert item["owner_department_id"] == "dept-fin"
    assert item["shared_department_ids"] == ["dept-ops"]
    assert item["business_category_id"] == "cat-budget"
    assert item["role_restriction"] == "employee"
    assert item["is_public_restricted"] is True
    assert item["confidentiality_level"] == "confidential"
    assert item["document_status"] == "published"
    mock_list_documents.assert_called_once_with(1, 10, current_user=current_user)


def test_upload_forwards_governance_fields_and_actor_context(monkeypatch):
    current_user = {"id": "user-1", "role_code": "employee", "primary_department_id": "dept-fin"}
    mock_upload = Mock(
        return_value={
            "id": "doc-1",
            "filename": "budget.pdf",
            "file_type": ".pdf",
            "visibility_scope": "public",
            "owner_department_id": "dept-fin",
            "shared_department_ids": ["dept-fin", "dept-ops"],
            "business_category_id": "cat-budget",
            "role_restriction": "employee",
            "is_public_restricted": True,
            "confidentiality_level": "confidential",
            "document_status": "published",
        }
    )
    monkeypatch.setattr(document_api.document_service, "upload", mock_upload)
    upload = UploadFile(filename="budget.pdf", file=io.BytesIO(b"%PDF-1.4"))

    body = asyncio.run(
        document_api.upload_document(
            file=upload,
            visibility_scope="public",
            owner_department_id="dept-fin",
            shared_department_ids=["dept-fin", "dept-ops"],
            business_category_id="cat-budget",
            role_restriction="employee",
            is_public_restricted=True,
            confidentiality_level="confidential",
            document_status="published",
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    args, kwargs = mock_upload.call_args
    assert args[0] == "budget.pdf"
    assert kwargs["current_user"] == current_user
    assert kwargs["governance_metadata"] == {
        "visibility_scope": "public",
        "owner_department_id": "dept-fin",
        "shared_department_ids": ["dept-fin", "dept-ops"],
        "business_category_id": "cat-budget",
        "role_restriction": "employee",
        "is_public_restricted": True,
        "confidentiality_level": "confidential",
        "document_status": "published",
    }


def test_document_detail_content_reader_and_file_forward_current_user(monkeypatch, tmp_path: Path):
    current_user = {"id": "user-1", "role_code": "employee", "department_ids": ["dept-fin"]}
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    mock_get_document = Mock(
        return_value={
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(pdf_path),
            "file_type": ".pdf",
            "file_available": True,
        }
    )
    mock_get_payload = Mock(return_value={"id": "doc-1", "content_record": {}, "segments": [], "artifacts": []})
    mock_get_reader = Mock(return_value={"document_id": "doc-1", "blocks": [], "best_anchor": {"block_id": "doc-1#0"}})
    monkeypatch.setattr(document_api.document_service, "get_document", mock_get_document)
    monkeypatch.setattr(document_api.document_service, "get_document_payload", mock_get_payload)
    monkeypatch.setattr(document_api.document_service, "get_reader_payload", mock_get_reader)

    detail = asyncio.run(document_api.get_document_detail("doc-1", current_user=current_user))
    content = asyncio.run(document_api.get_document_content("doc-1", current_user=current_user))
    reader = asyncio.run(
        document_api.get_document_reader("doc-1", query="预算", anchor_block_id="doc-1#0", current_user=current_user)
    )
    file_response = asyncio.run(document_api.get_document_file("doc-1", current_user=current_user))

    assert detail["code"] == 200
    assert content["code"] == 200
    assert reader["code"] == 200
    assert file_response.media_type == "application/pdf"
    mock_get_document.assert_any_call("doc-1", current_user=current_user)
    mock_get_payload.assert_called_once_with("doc-1", current_user=current_user)
    mock_get_reader.assert_called_once_with(
        "doc-1",
        query="预算",
        anchor_block_id="doc-1#0",
        current_user=current_user,
    )


def test_update_document_metadata_forwards_governed_fields(monkeypatch):
    current_user = {"id": "user-admin", "role_code": "department_admin", "managed_department_ids": ["dept-fin"]}
    mock_update_document_metadata = Mock(
        return_value={
            "id": "doc-1",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin",
            "shared_department_ids": ["dept-ops"],
            "business_category_id": "cat-budget",
            "role_restriction": "employee",
            "is_public_restricted": False,
            "confidentiality_level": "internal",
            "document_status": "published",
        }
    )
    monkeypatch.setattr(document_api.document_service, "update_document_metadata", mock_update_document_metadata)
    request = document_api.UpdateDocumentRequest(
        visibility_scope="department",
        owner_department_id="dept-fin",
        shared_department_ids=["dept-ops"],
        business_category_id="cat-budget",
        role_restriction="employee",
        is_public_restricted=False,
        confidentiality_level="internal",
        document_status="published",
    )

    body = asyncio.run(document_api.update_document_metadata("doc-1", request, current_user=current_user))

    assert body["code"] == 200
    mock_update_document_metadata.assert_called_once_with(
        "doc-1",
        {
            "visibility_scope": "department",
            "owner_department_id": "dept-fin",
            "shared_department_ids": ["dept-ops"],
            "business_category_id": "cat-budget",
            "role_restriction": "employee",
            "is_public_restricted": False,
            "confidentiality_level": "internal",
            "document_status": "published",
        },
        current_user=current_user,
    )


def test_document_service_applies_governance_defaults_with_actor_context():
    service = DocumentService()
    normalized = service._apply_governance_defaults(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
        },
        current_user={
            "id": "user-1",
            "primary_department_id": "dept-fin",
            "role_code": "employee",
        },
    )

    assert normalized["visibility_scope"] == "department"
    assert normalized["owner_department_id"] == "dept-fin"
    assert normalized["shared_department_ids"] == []
    assert normalized["business_category_id"] is None
    assert normalized["role_restriction"] is None
    assert normalized["is_public_restricted"] is False
    assert normalized["confidentiality_level"] == "internal"
    assert normalized["document_status"] == "draft"


def test_document_service_list_documents_filters_visible_documents(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_all_documents",
        lambda: [
            {"id": "doc-visible", "filename": "visible.pdf"},
            {"id": "doc-hidden", "filename": "hidden.pdf"},
        ],
    )
    monkeypatch.setattr(
        document_service_module.authorization_service,
        "can_view_document",
        lambda user, document: document["id"] == "doc-visible",
    )
    monkeypatch.setattr(
        document_service_module,
        "enrich_document_file_state",
        lambda doc_info, persist=True: {**doc_info, "file_available": True},
    )

    payload = DocumentService().list_documents(
        page=1,
        page_size=10,
        current_user={"id": "user-1", "role_code": "employee"},
    )

    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == ["doc-visible"]


def test_document_service_get_document_denies_unviewable_document(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filename": "restricted.pdf"},
    )
    monkeypatch.setattr(
        document_service_module.authorization_service,
        "can_view_document",
        lambda user, document: False,
    )

    try:
        DocumentService().get_document(
            "doc-1",
            current_user={"id": "user-1", "role_code": "employee", "department_ids": ["dept-fin"]},
        )
    except AppServiceError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("expected unauthorized access to raise AppServiceError")
