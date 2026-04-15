import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.organization as organization_api  # noqa: E402


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
