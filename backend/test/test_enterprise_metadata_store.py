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


def test_upsert_document_persists_enterprise_columns_in_documents_row(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )

    doc_info = {
        "id": "doc-enterprise",
        "filename": "governance.pdf",
        "filepath": "/tmp/governance.pdf",
        "file_type": ".pdf",
        "visibility_scope": "shared",
        "owner_department_id": "dept-fin",
        "business_category_id": "cat-budget",
        "role_restriction": "department_admin",
        "confidentiality_level": "confidential",
        "document_status": "published",
        "is_public_restricted": 1,
    }
    assert store.upsert_document(doc_info, mirror=False)

    updated = {
        **doc_info,
        "owner_department_id": "dept-legal",
        "business_category_id": "cat-contract",
        "role_restriction": "audit_readonly",
        "confidentiality_level": "strict",
        "document_status": "archived",
        "is_public_restricted": 0,
    }
    assert store.upsert_document(updated, mirror=False)

    with store._connect() as connection:
        row = connection.execute(
            """
            SELECT
                visibility_scope,
                owner_department_id,
                business_category_id,
                role_restriction,
                confidentiality_level,
                document_status,
                is_public_restricted
            FROM documents
            WHERE id = ?
            """,
            ("doc-enterprise",),
        ).fetchone()

    assert row["visibility_scope"] == "shared"
    assert row["owner_department_id"] == "dept-legal"
    assert row["business_category_id"] == "cat-contract"
    assert row["role_restriction"] == "audit_readonly"
    assert row["confidentiality_level"] == "strict"
    assert row["document_status"] == "archived"
    assert row["is_public_restricted"] == 0


def test_delete_document_removes_document_shared_departments(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    assert store.upsert_document(
        {
            "id": "doc-delete",
            "filename": "delete.pdf",
            "filepath": "/tmp/delete.pdf",
            "file_type": ".pdf",
        },
        mirror=False,
    )
    store.replace_document_shared_departments("doc-delete", ["dept-a", "dept-b"])

    assert store.list_document_shared_departments("doc-delete") == ["dept-a", "dept-b"]
    assert store.delete_document("doc-delete", mirror=False)
    assert store.list_document_shared_departments("doc-delete") == []


def test_upsert_user_reuses_existing_row_by_username(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )

    first = store.upsert_user(
        {
            "id": "user-1",
            "username": "alice",
            "password_hash": "hash-1",
            "display_name": "Alice",
            "role_code": "employee",
        }
    )
    second = store.upsert_user(
        {
            "id": "user-2",
            "username": "alice",
            "password_hash": "hash-2",
            "display_name": "Alice Updated",
            "role_code": "department_admin",
        }
    )

    assert second["id"] == first["id"]
    assert second["password_hash"] == "hash-2"
    assert second["display_name"] == "Alice Updated"
    assert second["role_code"] == "department_admin"
    with store._connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()
    assert row["count"] == 1


def test_upsert_business_category_updates_scope_department_and_creator(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    store.upsert_business_category(
        {
            "id": "cat-governance",
            "name": "治理类",
            "scope_type": "system",
            "department_id": None,
            "status": "enabled",
            "sort_order": 10,
            "created_by": "system",
        }
    )
    store.upsert_business_category(
        {
            "id": "cat-governance",
            "name": "治理类",
            "scope_type": "department",
            "department_id": "dept-fin",
            "status": "enabled",
            "sort_order": 11,
            "created_by": "user-admin",
        }
    )

    department_scoped = store.list_business_categories(scope_type="department", department_id="dept-fin")
    assert any(
        item["id"] == "cat-governance" and item["created_by"] == "user-admin"
        for item in department_scoped
    )
    assert all(
        item["id"] != "cat-governance"
        for item in store.list_business_categories(scope_type="system")
    )


def test_get_and_list_documents_include_enterprise_default_fields(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    assert store.upsert_document(
        {
            "id": "doc-defaults",
            "filename": "defaults.pdf",
            "filepath": "/tmp/defaults.pdf",
            "file_type": ".pdf",
        },
        mirror=False,
    )

    one = store.get_document("doc-defaults")
    listed = next(item for item in store.list_documents() if item["id"] == "doc-defaults")

    for doc in (one, listed):
        assert doc["visibility_scope"] == "department"
        assert doc["owner_department_id"] is None
        assert doc["business_category_id"] is None
        assert doc["role_restriction"] is None
        assert doc["confidentiality_level"] == "internal"
        assert doc["document_status"] == "draft"
        assert doc["is_public_restricted"] == 0
