import asyncio
import os
import sys
from unittest.mock import Mock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api as api_module  # noqa: E402
import api.organization as organization_api  # noqa: E402
from app.services.errors import AppServiceError  # noqa: E402
from app.services.organization_service import OrganizationService  # noqa: E402


def test_organization_routes_are_top_level_spec_paths():
    route_methods_by_path: dict[str, set[str]] = {}
    for route in api_module.router.routes:
        if not hasattr(route, "methods"):
            continue
        route_methods_by_path.setdefault(route.path, set()).update(route.methods or set())

    assert "POST" in route_methods_by_path.get("/users", set())
    assert "GET" in route_methods_by_path.get("/users", set())
    assert "GET" in route_methods_by_path.get("/departments", set())
    assert "GET" in route_methods_by_path.get("/roles", set())
    assert "/organization/users" not in route_methods_by_path


def test_create_user_forwards_primary_and_collaborative_departments(monkeypatch):
    current_user = {"id": "user-admin", "role_code": "system_admin"}
    request = organization_api.CreateUserRequest(
        username="alice",
        password="Secret@123",
        display_name="Alice",
        role_code="employee",
        primary_department_id="dept-fin",
        collaborative_department_ids=["dept-risk", "dept-ops"],
    )
    mock_create_user = Mock(
        return_value={
            "id": "user-alice",
            "username": "alice",
            "display_name": "Alice",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
            "collaborative_department_ids": ["dept-risk", "dept-ops"],
        }
    )
    monkeypatch.setattr(organization_api.organization_service, "create_user", mock_create_user)

    body = asyncio.run(organization_api.create_user(request, current_user=current_user))

    assert body["code"] == 200
    assert body["data"]["username"] == "alice"
    mock_create_user.assert_called_once_with(
        {
            "username": "alice",
            "password": "Secret@123",
            "display_name": "Alice",
            "role_code": "employee",
            "primary_department_id": "dept-fin",
            "collaborative_department_ids": ["dept-risk", "dept-ops"],
            "status": "enabled",
        },
        current_user=current_user,
    )


def test_list_users_forwards_paging_and_returns_paginated_payload(monkeypatch):
    current_user = {"id": "user-admin", "role_code": "system_admin"}
    mock_list_users = Mock(
        return_value={
            "items": [
                {
                    "id": "user-1",
                    "username": "alice",
                    "display_name": "Alice",
                    "role_code": "employee",
                    "primary_department_id": "dept-fin",
                    "collaborative_department_ids": ["dept-risk"],
                    "status": "enabled",
                }
            ],
            "total": 1,
            "page": 2,
            "page_size": 5,
            "total_pages": 1,
        }
    )
    monkeypatch.setattr(organization_api.organization_service, "list_users", mock_list_users)

    body = asyncio.run(
        organization_api.list_users(
            page=2,
            page_size=5,
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"]["items"][0]["username"] == "alice"
    assert body["data"]["page"] == 2
    assert body["data"]["page_size"] == 5
    mock_list_users.assert_called_once_with(2, 5, current_user=current_user)


def test_list_departments_forwards_actor_context(monkeypatch):
    current_user = {"id": "user-1", "role_code": "employee"}
    mock_list_departments = Mock(
        return_value=[
            {"id": "dept-fin", "name": "Finance"},
            {"id": "dept-ops", "name": "Operations"},
        ]
    )
    monkeypatch.setattr(organization_api.organization_service, "list_departments", mock_list_departments)

    body = asyncio.run(organization_api.list_departments(current_user=current_user))

    assert body["code"] == 200
    assert len(body["data"]) == 2
    mock_list_departments.assert_called_once_with(current_user=current_user)


def test_list_roles_forwards_actor_context(monkeypatch):
    current_user = {"id": "user-1", "role_code": "employee"}
    mock_list_roles = Mock(
        return_value=[
            {"code": "system_admin", "name": "系统管理员"},
            {"code": "employee", "name": "普通员工"},
        ]
    )
    monkeypatch.setattr(organization_api.organization_service, "list_roles", mock_list_roles)

    body = asyncio.run(organization_api.list_roles(current_user=current_user))

    assert body["code"] == 200
    assert body["data"][0]["code"] == "system_admin"
    mock_list_roles.assert_called_once_with(current_user=current_user)


def test_create_user_rejects_duplicate_username():
    store = Mock()
    store.get_user_by_username.return_value = {"id": "user-existing", "username": "alice"}
    store.upsert_user.return_value = {
        "id": "user-existing",
        "username": "alice",
        "display_name": "Alice",
        "status": "enabled",
        "role_code": "employee",
    }
    auth_service = Mock()
    auth_service.hash_password.return_value = "hashed"
    service = OrganizationService(store=store, auth_service=auth_service)

    with pytest.raises(AppServiceError) as exc_info:
        service.create_user(
            {
                "username": "alice",
                "password": "Secret@123",
                "display_name": "Alice",
                "role_code": "employee",
                "primary_department_id": "dept-fin",
                "collaborative_department_ids": [],
                "status": "enabled",
            },
            current_user={"id": "user-admin", "role_code": "system_admin"},
    )

    assert exc_info.value.code == 2001
    assert "用户名已存在" in str(exc_info.value.detail)
    store.upsert_user.assert_not_called()
    store.replace_user_department_memberships.assert_not_called()
    auth_service.hash_password.assert_not_called()
