import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.metadata_store import DocumentMetadataStore
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationService


def test_can_view_and_manage_document_permission_matrix():
    service = AuthorizationService()
    employee_user = {
        "id": "user-employee",
        "role_code": "employee",
        "department_ids": ["dept-fin", "dept-risk"],
    }
    department_admin_user = {
        "id": "user-admin",
        "role_code": "department_admin",
        "department_ids": ["dept-fin"],
        "managed_department_ids": ["dept-fin"],
    }
    system_admin_user = {
        "id": "user-sysadmin",
        "role_code": "system_admin",
        "department_ids": [],
    }

    public_document = {
        "id": "doc-public",
        "visibility_scope": "public",
        "owner_department_id": None,
        "shared_department_ids": [],
        "role_restriction": None,
    }
    public_restricted_document = {
        "id": "doc-public-restricted",
        "visibility_scope": "public",
        "owner_department_id": None,
        "shared_department_ids": ["dept-ops"],
        "role_restriction": None,
    }
    department_document = {
        "id": "doc-dept",
        "visibility_scope": "department",
        "owner_department_id": "dept-fin",
        "shared_department_ids": [],
        "role_restriction": None,
    }
    role_restricted_document = {
        "id": "doc-role-restricted",
        "visibility_scope": "public",
        "owner_department_id": None,
        "shared_department_ids": [],
        "role_restriction": "department_admin",
    }

    assert service.can_view_document(system_admin_user, public_restricted_document) is True
    assert service.can_manage_document(system_admin_user, public_restricted_document) is True

    assert service.can_view_document(employee_user, public_document) is True
    assert service.can_view_document(employee_user, public_restricted_document) is False
    assert service.can_view_document(employee_user, department_document) is True
    assert service.can_view_document(employee_user, role_restricted_document) is False
    assert service.can_manage_document(employee_user, department_document) is False

    assert service.can_view_document(department_admin_user, role_restricted_document) is True
    assert service.can_manage_document(department_admin_user, department_document) is True
    assert (
        service.can_manage_document(
            department_admin_user,
            {
                "id": "doc-other",
                "visibility_scope": "department",
                "owner_department_id": "dept-ops",
                "shared_department_ids": [],
                "role_restriction": None,
            },
        )
        is False
    )


def test_list_visible_document_ids_filters_documents():
    service = AuthorizationService()
    user = {
        "id": "user-1",
        "role_code": "employee",
        "department_ids": ["dept-fin"],
    }
    documents = [
        {
            "id": "doc-public",
            "visibility_scope": "public",
            "owner_department_id": None,
            "shared_department_ids": [],
            "role_restriction": None,
        },
        {
            "id": "doc-public-restricted",
            "visibility_scope": "public",
            "owner_department_id": None,
            "shared_department_ids": ["dept-fin"],
            "role_restriction": None,
        },
        {
            "id": "doc-department-owner",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin",
            "shared_department_ids": [],
            "role_restriction": None,
        },
        {
            "id": "doc-department-denied",
            "visibility_scope": "department",
            "owner_department_id": "dept-ops",
            "shared_department_ids": [],
            "role_restriction": None,
        },
        {
            "id": "doc-role-restricted",
            "visibility_scope": "public",
            "owner_department_id": None,
            "shared_department_ids": [],
            "role_restriction": "department_admin",
        },
    ]

    visible = service.list_visible_document_ids(user, documents)

    assert visible == {"doc-public", "doc-public-restricted", "doc-department-owner"}


def test_audit_service_record_persists_user_snapshot_and_metadata(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    service = AuditService(store=store)
    user = {
        "id": "user-1",
        "username": "alice",
        "primary_department_id": "dept-fin",
        "role_code": "employee",
    }

    first_id = service.record(
        action_type="login_success",
        target_type="auth",
        target_id="alice",
        result="success",
        user=user,
        ip_address="203.0.113.10",
        metadata={"channel": "password"},
    )
    second_id = service.record(
        action_type="login_failure",
        target_type="auth",
        target_id="alice",
        result="failure",
        user=None,
        ip_address="203.0.113.10",
        metadata={"reason": "bad_password"},
    )

    logs = store.list_audit_logs(limit=10)

    assert first_id
    assert second_id
    assert first_id != second_id
    by_action = {item["action_type"]: item for item in logs}
    success_log = by_action["login_success"]
    failure_log = by_action["login_failure"]
    assert success_log["user_id"] == "user-1"
    assert success_log["username_snapshot"] == "alice"
    assert success_log["department_id"] == "dept-fin"
    assert success_log["role_code"] == "employee"
    assert success_log["ip_address"] == "203.0.113.10"
    assert success_log["metadata_json"] == {"channel": "password"}
    assert failure_log["user_id"] is None
    assert failure_log["metadata_json"] == {"reason": "bad_password"}
