from pathlib import Path

from app.infra.metadata_store import DocumentMetadataStore


def test_initialize_enterprise_schema_seeds_roles_departments_categories_and_admin(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )

    summary = store.ensure_enterprise_defaults(admin_password_hash="salt$hash")

    assert summary["admin_username"] == "admin"
    assert {item["code"] for item in store.list_roles()} == {
        "system_admin",
        "department_admin",
        "employee",
        "audit_readonly",
    }
    assert "待归属" in {item["name"] for item in store.list_departments()}
    assert "待整理" in {
        item["name"] for item in store.list_business_categories(scope_type="system")
    }
    assert store.get_user_by_username("admin")["role_code"] == "system_admin"


def test_document_shared_departments_and_sessions_roundtrip(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    store.ensure_enterprise_defaults(admin_password_hash="salt$hash")
    store.upsert_document(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": "/tmp/budget.pdf",
            "file_type": ".pdf",
            "visibility_scope": "department",
            "owner_department_id": "dept-fin",
            "business_category_id": "cat-budget",
        },
        mirror=False,
    )

    store.replace_document_shared_departments("doc-1", ["dept-ops", "dept-legal"])
    token = store.create_auth_session(
        user_id="user-1",
        token="token-1",
        expires_at="2026-04-16T00:00:00",
    )

    assert token == "token-1"
    assert store.list_document_shared_departments("doc-1") == ["dept-ops", "dept-legal"]
    assert store.get_auth_session("token-1")["user_id"] == "user-1"
