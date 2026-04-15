import asyncio
import json
import os
import sys
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api as api_module  # noqa: E402
import api.dependencies as api_dependencies  # noqa: E402
import api.directory as directory_api  # noqa: E402
from app.services.errors import AppServiceError  # noqa: E402


def create_test_client() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(api_module.BusinessException, api_module.business_exception_handler)
    app.add_exception_handler(RequestValidationError, api_module.validation_exception_handler)
    app.add_exception_handler(Exception, api_module.generic_exception_handler)
    app.include_router(api_module.router, prefix="/api/v1")
    return app


def request_app(
    app: FastAPI,
    method: str,
    path: str,
    *,
    query_string: str = "",
    headers: dict | None = None,
) -> tuple[int, dict]:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("latin-1"), str(value).encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("utf-8"),
        "headers": raw_headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
    }
    response = {"status": None, "body": b""}
    received = {"done": False}

    async def receive():
        if not received["done"]:
            received["done"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            response["status"] = message["status"]
        if message["type"] == "http.response.body":
            response["body"] += message.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return int(response["status"]), json.loads(response["body"].decode("utf-8"))


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
    with pytest.raises(AppServiceError) as exc_info:
        service.build_workspace(current_user=None)
    assert exc_info.value.code == 401


def test_directory_workspace_route_requires_authenticated_user():
    app = create_test_client()

    status, body = request_app(app, "GET", "/api/v1/directory/workspace")

    assert status == 401
    assert body["code"] == 401


def test_directory_workspace_route_translates_service_errors(monkeypatch):
    app = create_test_client()
    monkeypatch.setattr(
        api_dependencies.auth_service,
        "get_current_actor",
        Mock(return_value={"id": "user-1", "role_code": "employee", "primary_department_id": "dept-fin"}),
    )
    monkeypatch.setattr(
        directory_api.directory_service,
        "build_workspace",
        Mock(side_effect=AppServiceError(2001, "visibility_scope 非法")),
    )

    status, body = request_app(
        app,
        "GET",
        "/api/v1/directory/workspace",
        query_string="visibility_scope=invalid",
        headers={"Authorization": "Bearer token-1"},
    )

    assert status == 400
    assert body["code"] == 2001
    assert body["data"]["detail"] == "visibility_scope 非法"


def test_directory_workspace_keeps_documents_reachable_for_disabled_categories(monkeypatch):
    from app.services.directory_service import DirectoryService  # noqa: E402

    monkeypatch.setattr(
        "app.services.directory_service.get_all_documents",
        lambda: [
            {
                "id": "doc-legacy-1",
                "filename": "历史预算办法.docx",
                "file_type": ".docx",
                "visibility_scope": "department",
                "owner_department_id": "dept-fin",
                "shared_department_ids": [],
                "business_category_id": "cat-legacy",
            }
        ],
    )

    service = DirectoryService()
    service.organization_service.list_departments = lambda current_user=None: [
        {"id": "dept-fin", "name": "财务部"},
    ]
    service.category_service.store.list_business_categories = lambda scope_type=None, department_id=None: (
        []
        if scope_type == "system"
        else [
            {
                "id": "cat-legacy",
                "name": "历史预算",
                "scope_type": "department",
                "department_id": "dept-fin",
                "status": "disabled",
                "sort_order": 99,
            }
        ]
    )

    dept_payload = service.build_workspace(
        visibility_scope="department",
        department_id="dept-fin",
        current_user={
            "id": "user-1",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
        },
    )
    assert [folder["label"] for folder in dept_payload["folders"]] == ["历史预算"]

    scoped_payload = service.build_workspace(
        visibility_scope="department",
        department_id="dept-fin",
        business_category_id="cat-legacy",
        current_user={
            "id": "user-1",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
        },
    )
    assert [doc["id"] for doc in scoped_payload["documents"]] == ["doc-legacy-1"]
    assert scoped_payload["documents"][0]["business_category_name"] == "历史预算"


def test_directory_workspace_rejects_disabled_categories_without_visible_documents(monkeypatch):
    from app.services.directory_service import DirectoryService  # noqa: E402

    monkeypatch.setattr("app.services.directory_service.get_all_documents", lambda: [])

    service = DirectoryService()
    service.organization_service.list_departments = lambda current_user=None: [
        {"id": "dept-fin", "name": "财务部"},
    ]
    service.category_service.store.list_business_categories = lambda scope_type=None, department_id=None: (
        []
        if scope_type == "system"
        else [
            {
                "id": "cat-hidden-disabled",
                "name": "停用分类",
                "scope_type": "department",
                "department_id": "dept-fin",
                "status": "disabled",
                "sort_order": 99,
            }
        ]
    )

    with pytest.raises(AppServiceError) as exc_info:
        service.build_workspace(
            visibility_scope="department",
            department_id="dept-fin",
            business_category_id="cat-hidden-disabled",
            current_user={
                "id": "user-1",
                "role_code": "employee",
                "primary_department_id": "dept-fin",
            },
        )

    assert exc_info.value.code == 1001
