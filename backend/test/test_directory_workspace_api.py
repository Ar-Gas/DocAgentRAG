import os
import sys

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_directory_workspace_locks_inaccessible_departments_and_builds_breadcrumbs(monkeypatch):
    """
    Contract test for the governed directory explorer workspace read model.

    Locks:
    - Tree must show both "公共文档" and "部门文档" at root.
    - Inaccessible departments still appear but are locked.
    - Folder contents, breadcrumbs, and current_scope match the requested scope.
    """

    from app.services.directory_service import DirectoryService  # noqa: E402

    monkeypatch.setattr(
        "app.services.directory_service.get_all_documents",
        lambda: [
            {
                "id": "doc-public-1",
                "filename": "制度总则.pdf",
                "file_type": ".pdf",
                "visibility_scope": "public",
                "business_category_id": "cat-policy",
                "owner_department_id": None,
                "shared_department_ids": [],
            },
            {
                "id": "doc-fin-1",
                "filename": "预算编制办法.docx",
                "file_type": ".docx",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-budget",
            },
        ],
    )

    service = DirectoryService()
    service.organization_service.list_departments = lambda current_user=None: [
        {"id": "dept-fin", "name": "财务部"},
        {"id": "dept-hr", "name": "人事部"},
    ]
    service.category_service.store.list_business_categories = lambda scope_type=None, department_id=None: (
        [
            {
                "id": "cat-policy",
                "name": "制度流程",
                "scope_type": "system",
                "status": "enabled",
                "sort_order": 1,
            }
        ]
        if scope_type == "system"
        else [
            {
                "id": "cat-budget",
                "name": "预算管理",
                "scope_type": "department",
                "department_id": "dept-fin",
                "status": "enabled",
                "sort_order": 1,
            }
        ]
    )

    root_payload = service.build_workspace(
        current_user={
            "id": "user-1",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
        }
    )

    assert root_payload["current_scope"]["scope_key"] == "root"
    assert root_payload["breadcrumbs"][0]["label"] == "全局目录"
    assert [node["label"] for node in root_payload["tree"]] == ["公共文档", "部门文档"]

    department_root = root_payload["tree"][1]
    locked_departments = [item for item in department_root["children"] if item.get("locked")]
    assert locked_departments
    assert locked_departments[0]["department_id"] == "dept-hr"

    dept_payload = service.build_workspace(
        visibility_scope="department",
        current_user={
            "id": "user-1",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
        },
    )
    assert dept_payload["current_scope"]["visibility_scope"] == "department"
    assert dept_payload["current_scope"]["department_id"] is None
    assert dept_payload["folders"]
    assert any(folder.get("locked") for folder in dept_payload["folders"])

    scoped_payload = service.build_workspace(
        visibility_scope="department",
        department_id="dept-fin",
        business_category_id="cat-budget",
        current_user={
            "id": "user-1",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
        },
    )
    assert scoped_payload["current_scope"]["scope_key"] == "department:dept-fin:cat-budget"
    assert [crumb["label"] for crumb in scoped_payload["breadcrumbs"]] == [
        "全局目录",
        "部门文档",
        "财务部",
        "预算管理",
    ]
    assert scoped_payload["documents"][0]["id"] == "doc-fin-1"
    assert scoped_payload["documents"][0]["owner_department_name"] == "财务部"
    assert scoped_payload["documents"][0]["business_category_name"] == "预算管理"


def test_directory_workspace_rejects_unauthenticated_user():
    from app.services.directory_service import DirectoryService  # noqa: E402

    service = DirectoryService()
    with pytest.raises(Exception):
        service.build_workspace(current_user=None)

