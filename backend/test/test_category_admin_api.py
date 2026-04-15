import asyncio
import os
import sys
from unittest.mock import Mock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api as api_module  # noqa: E402
import api.categories as categories_api  # noqa: E402
from app.services.category_service import CategoryService  # noqa: E402
from app.services.errors import AppServiceError  # noqa: E402


def test_category_routes_use_explicit_system_department_and_patch_paths():
    route_methods_by_path: dict[str, set[str]] = {}
    for route in api_module.router.routes:
        if not hasattr(route, "methods"):
            continue
        route_methods_by_path.setdefault(route.path, set()).update(route.methods or set())

    assert "POST" in route_methods_by_path.get("/categories/system", set())
    assert "GET" in route_methods_by_path.get("/categories/system", set())
    assert "POST" in route_methods_by_path.get("/categories/department", set())
    assert "GET" in route_methods_by_path.get("/categories/department", set())
    assert "PATCH" in route_methods_by_path.get("/categories/{category_id}", set())


def test_create_department_category_forwards_department_admin_scope(monkeypatch):
    current_user = {
        "id": "user-admin",
        "role_code": "department_admin",
        "managed_department_ids": ["dept-fin"],
    }
    request = categories_api.CreateDepartmentCategoryRequest(
        name="财务制度",
        department_id="dept-fin",
        sort_order=10,
        status="enabled",
    )
    mock_create_department_category = Mock(
        return_value={
            "id": "cat-fin-rules",
            "name": "财务制度",
            "scope_type": "department",
            "department_id": "dept-fin",
            "sort_order": 10,
            "status": "enabled",
        }
    )
    monkeypatch.setattr(
        categories_api.category_service,
        "create_department_category",
        mock_create_department_category,
    )

    body = asyncio.run(
        categories_api.create_department_category(
            request=request,
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"]["scope_type"] == "department"
    assert body["data"]["department_id"] == "dept-fin"
    mock_create_department_category.assert_called_once_with(
        {
            "name": "财务制度",
            "department_id": "dept-fin",
            "sort_order": 10,
            "status": "enabled",
        },
        current_user=current_user,
    )


def test_create_system_category_forwards_system_scope(monkeypatch):
    current_user = {"id": "user-sys", "role_code": "system_admin"}
    request = categories_api.CreateSystemCategoryRequest(
        name="公司制度",
        sort_order=1,
        status="enabled",
    )
    mock_create_system_category = Mock(
        return_value={
            "id": "cat-system-policy",
            "name": "公司制度",
            "scope_type": "system",
            "department_id": None,
            "sort_order": 1,
            "status": "enabled",
        }
    )
    monkeypatch.setattr(
        categories_api.category_service,
        "create_system_category",
        mock_create_system_category,
    )

    body = asyncio.run(
        categories_api.create_system_category(
            request=request,
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"]["scope_type"] == "system"
    mock_create_system_category.assert_called_once_with(
        {"name": "公司制度", "sort_order": 1, "status": "enabled"},
        current_user=current_user,
    )


def test_list_department_categories_forwards_department_scope(monkeypatch):
    current_user = {"id": "user-admin", "role_code": "department_admin"}
    mock_list_department_categories = Mock(
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
    monkeypatch.setattr(
        categories_api.category_service,
        "list_department_categories",
        mock_list_department_categories,
    )

    body = asyncio.run(
        categories_api.list_department_categories(
            department_id="dept-fin",
            status="enabled",
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"][0]["id"] == "cat-fin-rules"
    mock_list_department_categories.assert_called_once_with(
        department_id="dept-fin",
        status="enabled",
        current_user=current_user,
    )


def test_list_department_categories_requires_department_admin_scope():
    store = Mock()
    service = CategoryService(store=store)

    with pytest.raises(AppServiceError) as exc_info:
        service.list_department_categories(
            department_id="dept-risk",
            current_user={
                "id": "user-admin",
                "role_code": "department_admin",
                "managed_department_ids": ["dept-fin"],
            },
        )

    assert exc_info.value.code == 401
    store.list_business_categories.assert_not_called()


def test_list_department_categories_allows_system_admin_any_department():
    store = Mock()
    store.list_business_categories.return_value = [
        {"id": "cat-risk", "scope_type": "department", "department_id": "dept-risk"}
    ]
    service = CategoryService(store=store)

    categories = service.list_department_categories(
        department_id="dept-risk",
        current_user={"id": "user-sys", "role_code": "system_admin"},
    )

    assert categories == [
        {"id": "cat-risk", "scope_type": "department", "department_id": "dept-risk"}
    ]
    store.list_business_categories.assert_called_once_with(
        scope_type="department",
        department_id="dept-risk",
    )


def test_update_category_forwards_patch_fields(monkeypatch):
    current_user = {"id": "user-sys", "role_code": "system_admin"}
    request = categories_api.UpdateCategoryRequest(
        name="公司制度-更新",
        status="disabled",
        sort_order=20,
    )
    mock_update_category = Mock(
        return_value={
            "id": "cat-system-policy",
            "name": "公司制度-更新",
            "scope_type": "system",
            "department_id": None,
            "sort_order": 20,
            "status": "disabled",
        }
    )
    monkeypatch.setattr(categories_api.category_service, "update_category", mock_update_category)

    body = asyncio.run(
        categories_api.update_category(
            category_id="cat-system-policy",
            request=request,
            current_user=current_user,
        )
    )

    assert body["code"] == 200
    assert body["data"]["status"] == "disabled"
    mock_update_category.assert_called_once_with(
        "cat-system-policy",
        {"name": "公司制度-更新", "status": "disabled", "sort_order": 20},
        current_user=current_user,
    )
