import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.categories as categories_api  # noqa: E402


def test_create_department_category_forwards_department_admin_scope(monkeypatch):
    current_user = {
        "id": "user-admin",
        "role_code": "department_admin",
        "managed_department_ids": ["dept-fin"],
    }
    request = categories_api.CreateCategoryRequest(
        name="财务制度",
        scope_type="department",
        department_id="dept-fin",
        sort_order=10,
        status="enabled",
    )
    mock_create_category = Mock(
        return_value={
            "id": "cat-fin-rules",
            "name": "财务制度",
            "scope_type": "department",
            "department_id": "dept-fin",
            "sort_order": 10,
            "status": "enabled",
        }
    )
    monkeypatch.setattr(categories_api.category_service, "create_category", mock_create_category)

    body = asyncio.run(categories_api.create_category(request, current_user=current_user))

    assert body["code"] == 200
    assert body["data"]["scope_type"] == "department"
    assert body["data"]["department_id"] == "dept-fin"
    mock_create_category.assert_called_once_with(
        {
            "name": "财务制度",
            "scope_type": "department",
            "department_id": "dept-fin",
            "sort_order": 10,
            "status": "enabled",
        },
        current_user=current_user,
    )


def test_create_system_category_forwards_system_scope(monkeypatch):
    current_user = {"id": "user-sys", "role_code": "system_admin"}
    request = categories_api.CreateCategoryRequest(
        name="公司制度",
        scope_type="system",
        department_id=None,
        sort_order=1,
        status="enabled",
    )
    mock_create_category = Mock(
        return_value={
            "id": "cat-system-policy",
            "name": "公司制度",
            "scope_type": "system",
            "department_id": None,
            "sort_order": 1,
            "status": "enabled",
        }
    )
    monkeypatch.setattr(categories_api.category_service, "create_category", mock_create_category)

    body = asyncio.run(categories_api.create_category(request, current_user=current_user))

    assert body["code"] == 200
    assert body["data"]["scope_type"] == "system"
    mock_create_category.assert_called_once()


def test_list_categories_forwards_scope_filters(monkeypatch):
    current_user = {"id": "user-1", "role_code": "employee"}
    mock_list_categories = Mock(
        return_value=[
            {
                "id": "cat-fin-rules",
                "name": "财务制度",
                "scope_type": "department",
                "department_id": "dept-fin",
                "sort_order": 10,
                "status": "enabled",
            }
        ]
    )
    monkeypatch.setattr(categories_api.category_service, "list_categories", mock_list_categories)

    body = asyncio.run(
        categories_api.list_categories(
            scope_type="department",
            department_id="dept-fin",
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"][0]["id"] == "cat-fin-rules"
    mock_list_categories.assert_called_once_with(
        scope_type="department",
        department_id="dept-fin",
        current_user=current_user,
    )
