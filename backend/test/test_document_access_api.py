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


def test_document_list_builds_directory_name_maps_once_per_request(monkeypatch):
    current_user = {"id": "user-1", "role_code": "employee", "department_ids": ["dept-fin"]}
    mock_list_documents = Mock(
        return_value={
            "items": [
                {
                    "id": "doc-1",
                    "filename": "budget.pdf",
                    "file_type": ".pdf",
                    "visibility_scope": "department",
                    "owner_department_id": "dept-fin",
                    "business_category_id": "cat-budget",
                },
                {
                    "id": "doc-2",
                    "filename": "policy.pdf",
                    "file_type": ".pdf",
                    "visibility_scope": "public",
                    "owner_department_id": None,
                    "business_category_id": "cat-policy",
                },
            ],
            "total": 2,
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        }
    )
    calls = {"count": 0}

    def fake_directory_name_maps():
        calls["count"] += 1
        return (
            {"dept-fin": "财务部"},
            {"cat-budget": "预算管理", "cat-policy": "制度流程"},
        )

    monkeypatch.setattr(document_api.document_service, "list_documents", mock_list_documents)
    monkeypatch.setattr(document_api, "_directory_name_maps", fake_directory_name_maps)

    body = asyncio.run(
        document_api.get_document_list(
            page=1,
            page_size=10,
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert calls["count"] == 1


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
            shared_department_ids='["dept-fin", "dept-ops"]',
            business_category_id="cat-budget",
            role_restriction="employee",
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


def test_upload_rejects_json_shared_department_ids_with_non_list_type():
    current_user = {"id": "user-1", "role_code": "employee", "primary_department_id": "dept-fin"}
    mock_upload = Mock(return_value={"id": "doc-1"})
    original_upload = document_api.document_service.upload
    document_api.document_service.upload = mock_upload
    upload = UploadFile(filename="budget.pdf", file=io.BytesIO(b"%PDF-1.4"))

    try:
        asyncio.run(
            document_api.upload_document(
                file=upload,
                visibility_scope="public",
                owner_department_id="dept-fin",
                shared_department_ids='{"dept":"fin"}',
                business_category_id="cat-budget",
                role_restriction="employee",
                confidentiality_level="confidential",
                document_status="published",
                current_user=current_user,
            )
        )
    except document_api.BusinessException as exc:
        assert exc.code == 2001
    else:
        raise AssertionError("expected non-list JSON shared_department_ids to be rejected before upload")
    finally:
        document_api.document_service.upload = original_upload
    mock_upload.assert_not_called()


def test_upload_does_not_call_legacy_classifier(monkeypatch, tmp_path):
    import io
    import sys
    import types
    import app.services.document_service as document_service_module

    fake_classifier_module = types.ModuleType("utils.classifier")

    def _boom(*args, **kwargs):
        raise AssertionError("legacy classifier should not be called")

    fake_classifier_module.classify_document = _boom
    monkeypatch.setitem(sys.modules, "utils.classifier", fake_classifier_module)
    monkeypatch.setattr(document_service_module, "DOC_DIR", tmp_path)
    monkeypatch.setattr(
        document_service_module.DocumentService,
        "_trigger_block_reindex_best_effort",
        lambda self, document_id, context="upload": None,
        raising=False,
    )
    monkeypatch.setattr(
        document_service_module.ExtractionService,
        "extract",
        lambda self, filepath: types.SimpleNamespace(
            success=True,
            content="预算制度",
            parser_name="pdf",
            error=None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        document_service_module,
        "save_document_summary_for_classification",
        lambda filepath, full_content, parser_name, display_filename: (
            "doc-1",
            {
                "id": "doc-1",
                "filename": display_filename,
                "filepath": filepath,
                "file_type": ".pdf",
            },
        ),
    )
    monkeypatch.setattr(document_service_module, "save_document_to_chroma", lambda *args, **kwargs: True)
    monkeypatch.setattr(document_service_module, "update_document_info", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        document_service_module,
        "enrich_document_file_state",
        lambda doc_info, persist=True: {**doc_info, "file_available": True},
    )

    payload = document_service_module.DocumentService().upload(
        "budget.pdf",
        io.BytesIO(b"%PDF-1.4"),
        current_user={
            "id": "user-1",
            "primary_department_id": "dept-fin",
            "role_code": "employee",
        },
        governance_metadata={
            "visibility_scope": "department",
            "owner_department_id": "dept-fin",
            "shared_department_ids": [],
            "business_category_id": "cat-budget",
        },
    )

    assert payload["business_category_id"] == "cat-budget"
    assert payload.get("classification_result") in (None, "")


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
        use_owner_fallback=True,
    )

    assert normalized["visibility_scope"] == "department"
    assert normalized["owner_department_id"] == "dept-fin"
    assert normalized["shared_department_ids"] == []
    assert normalized["business_category_id"] == "cat-pending"
    assert normalized["role_restriction"] is None
    assert normalized["is_public_restricted"] is False
    assert normalized["confidentiality_level"] == "internal"
    assert normalized["document_status"] == "draft"


def test_document_service_derives_public_restriction_when_not_explicit():
    service = DocumentService()

    normalized = service._apply_governance_defaults(
        {
            "id": "doc-1",
            "visibility_scope": "public",
            "shared_department_ids": ["dept-fin"],
            "role_restriction": None,
        },
        current_user={"id": "user-1", "primary_department_id": "dept-fin"},
    )

    assert normalized["is_public_restricted"] is True


def test_document_service_governance_defaults_delegate_to_shared_normalizer(monkeypatch):
    service = DocumentService()
    mock_normalize = Mock(return_value={"id": "doc-1", "business_category_id": "cat-pending"})
    monkeypatch.setattr(document_service_module, "normalize_document_governance", mock_normalize, raising=False)

    payload = service._apply_governance_defaults(
        {"id": "doc-1"},
        current_user={"id": "user-1"},
    )

    assert payload["business_category_id"] == "cat-pending"
    mock_normalize.assert_called_once_with(
        {"id": "doc-1"},
        current_user={"id": "user-1"},
        use_owner_fallback=False,
    )


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


def test_document_service_get_document_does_not_gain_owner_access_from_actor_fallback(monkeypatch):
    monkeypatch.setattr(
        document_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "legacy.pdf",
            "visibility_scope": "department",
            "owner_department_id": None,
            "shared_department_ids": [],
        },
    )
    monkeypatch.setattr(
        document_service_module,
        "enrich_document_file_state",
        lambda doc_info, persist=True: {**doc_info, "file_available": True},
    )

    try:
        DocumentService().get_document(
            "doc-legacy",
            current_user={
                "id": "user-1",
                "role_code": "employee",
                "primary_department_id": "dept-fin",
                "department_ids": ["dept-fin"],
            },
        )
    except AppServiceError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("legacy owner fallback should not grant read permission")


def test_update_document_metadata_recomputes_public_restriction_when_omitted(monkeypatch):
    existing_doc = {
        "id": "doc-1",
        "filename": "doc.pdf",
        "visibility_scope": "department",
        "owner_department_id": "dept-fin",
        "shared_department_ids": [],
        "role_restriction": None,
        "is_public_restricted": False,
    }
    mock_update = Mock(return_value=True)
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: existing_doc)
    monkeypatch.setattr(document_service_module, "update_document_info", mock_update)
    service = DocumentService()
    monkeypatch.setattr(service, "get_document", Mock(return_value={"id": "doc-1", "is_public_restricted": True}))

    result = service.update_document_metadata(
        "doc-1",
        {
            "visibility_scope": "public",
            "role_restriction": "employee",
        },
        current_user={
            "id": "user-admin",
            "role_code": "department_admin",
            "department_ids": ["dept-fin"],
            "managed_department_ids": ["dept-fin"],
        },
    )

    assert result["is_public_restricted"] is True
    patch_payload = mock_update.call_args.args[1]
    assert patch_payload["is_public_restricted"] is True


def test_update_document_metadata_does_not_gain_manage_access_from_actor_fallback(monkeypatch):
    existing_doc = {
        "id": "doc-1",
        "filename": "doc.pdf",
        "visibility_scope": "department",
        "owner_department_id": None,
        "shared_department_ids": [],
        "role_restriction": None,
    }
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: existing_doc)
    monkeypatch.setattr(document_service_module, "update_document_info", Mock(return_value=True))
    service = DocumentService()
    monkeypatch.setattr(service, "get_document", Mock(return_value={"id": "doc-1"}))

    try:
        service.update_document_metadata(
            "doc-1",
            {"document_status": "published"},
            current_user={
                "id": "user-admin",
                "role_code": "department_admin",
                "primary_department_id": "dept-fin",
                "managed_department_ids": ["dept-fin"],
            },
        )
    except AppServiceError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("legacy owner fallback should not grant manage permission")


def test_update_document_metadata_denies_retarget_owner_department_outside_managed_scope(monkeypatch):
    existing_doc = {
        "id": "doc-1",
        "filename": "doc.pdf",
        "visibility_scope": "department",
        "owner_department_id": "dept-fin",
        "shared_department_ids": [],
        "role_restriction": None,
    }
    mock_update = Mock(return_value=True)
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: existing_doc)
    monkeypatch.setattr(document_service_module, "update_document_info", mock_update)
    service = DocumentService()
    monkeypatch.setattr(service, "get_document", Mock(return_value={"id": "doc-1"}))

    try:
        service.update_document_metadata(
            "doc-1",
            {"owner_department_id": "dept-ops"},
            current_user={
                "id": "user-admin",
                "role_code": "department_admin",
                "managed_department_ids": ["dept-fin"],
            },
        )
    except AppServiceError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("department_admin should not retarget owner department outside managed scope")

    mock_update.assert_not_called()


def test_update_document_metadata_denies_sharing_unmanaged_departments(monkeypatch):
    existing_doc = {
        "id": "doc-1",
        "filename": "doc.pdf",
        "visibility_scope": "department",
        "owner_department_id": "dept-fin",
        "shared_department_ids": [],
        "role_restriction": None,
    }
    mock_update = Mock(return_value=True)
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: existing_doc)
    monkeypatch.setattr(document_service_module, "update_document_info", mock_update)
    service = DocumentService()
    monkeypatch.setattr(service, "get_document", Mock(return_value={"id": "doc-1"}))

    try:
        service.update_document_metadata(
            "doc-1",
            {"shared_department_ids": ["dept-fin", "dept-ops"]},
            current_user={
                "id": "user-admin",
                "role_code": "department_admin",
                "managed_department_ids": ["dept-fin"],
            },
        )
    except AppServiceError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("department_admin should not share document to unmanaged departments")

    mock_update.assert_not_called()


def test_update_document_metadata_allows_unrelated_update_with_unchanged_unmanaged_shared(monkeypatch):
    existing_doc = {
        "id": "doc-1",
        "filename": "doc.pdf",
        "visibility_scope": "department",
        "owner_department_id": "dept-fin",
        "shared_department_ids": ["dept-ops"],
        "role_restriction": None,
    }
    mock_update = Mock(return_value=True)
    monkeypatch.setattr(document_service_module, "get_document_info", lambda document_id: existing_doc)
    monkeypatch.setattr(document_service_module, "update_document_info", mock_update)
    service = DocumentService()
    monkeypatch.setattr(service, "get_document", Mock(return_value={"id": "doc-1", "document_status": "published"}))

    result = service.update_document_metadata(
        "doc-1",
        {"document_status": "published"},
        current_user={
            "id": "user-admin",
            "role_code": "department_admin",
            "managed_department_ids": ["dept-fin"],
        },
    )

    assert result["document_status"] == "published"
    patch_payload = mock_update.call_args.args[1]
    assert patch_payload["document_status"] == "published"


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
