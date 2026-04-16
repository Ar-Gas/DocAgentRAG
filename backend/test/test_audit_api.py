import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api as api_module  # noqa: E402
import api.audit as audit_api  # noqa: E402
from app.infra.metadata_store import DocumentMetadataStore  # noqa: E402
from app.services.audit_service import AuditService  # noqa: E402


def test_audit_log_route_is_top_level_spec_path():
    route_methods_by_path: dict[str, set[str]] = {}
    for route in api_module.router.routes:
        if not hasattr(route, "methods"):
            continue
        route_methods_by_path.setdefault(route.path, set()).update(route.methods or set())

    assert "GET" in route_methods_by_path.get("/audit-logs", set())
    assert "/audit/logs" not in route_methods_by_path


def test_audit_service_allows_department_admin_to_list_logs():
    service = AuditService(store=Mock())
    service._ensure_list_permission({"id": "user-admin", "role_code": "department_admin"})


def test_list_audit_logs_forwards_filters_and_paging(monkeypatch):
    current_user = {"id": "user-audit", "role_code": "audit_readonly"}
    mock_list_logs = Mock(
        return_value={
            "items": [
                {
                    "id": "audit-1",
                    "action_type": "login_success",
                    "target_type": "auth",
                    "target_id": "alice",
                    "result": "success",
                }
            ],
            "total": 1,
            "page": 3,
            "page_size": 20,
            "total_pages": 1,
        }
    )
    monkeypatch.setattr(audit_api.audit_service, "list_logs", mock_list_logs)

    body = asyncio.run(
        audit_api.list_audit_logs(
            page=3,
            page_size=20,
            action_type="login_success",
            result="success",
            target_type="auth",
            target_id="alice",
            user_id="user-alice",
            username="alice",
            start_time="2026-04-01T00:00:00",
            end_time="2026-04-15T23:59:59",
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"]["items"][0]["action_type"] == "login_success"
    assert body["data"]["page"] == 3
    assert body["data"]["page_size"] == 20
    mock_list_logs.assert_called_once_with(
        page=3,
        page_size=20,
        action_type="login_success",
        result="success",
        target_type="auth",
        target_id="alice",
        user_id="user-alice",
        username="alice",
        start_time="2026-04-01T00:00:00",
        end_time="2026-04-15T23:59:59",
        current_user=current_user,
    )


def test_department_admin_list_logs_scopes_to_managed_departments_only(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    service = AuditService(store=store)

    store.insert_audit_log(
        {
            "id": "audit-fin",
            "department_id": "dept-fin",
            "action_type": "document_read",
            "target_type": "document",
            "target_id": "doc-1",
            "result": "success",
            "metadata_json": {},
            "created_at": "2026-04-15T10:00:00",
        }
    )
    store.insert_audit_log(
        {
            "id": "audit-ops",
            "department_id": "dept-ops",
            "action_type": "document_read",
            "target_type": "document",
            "target_id": "doc-2",
            "result": "success",
            "metadata_json": {},
            "created_at": "2026-04-15T10:01:00",
        }
    )
    store.insert_audit_log(
        {
            "id": "audit-null",
            "department_id": None,
            "action_type": "login_success",
            "target_type": "auth",
            "target_id": "alice",
            "result": "success",
            "metadata_json": {},
            "created_at": "2026-04-15T10:02:00",
        }
    )

    result = service.list_logs(
        page=1,
        page_size=20,
        current_user={
            "id": "user-dept-admin",
            "role_code": "department_admin",
            "managed_department_ids": ["dept-fin"],
        },
    )

    assert result["total"] == 1
    assert [item["id"] for item in result["items"]] == ["audit-fin"]
