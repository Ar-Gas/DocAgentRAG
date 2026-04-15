from app.infra.metadata_store import get_metadata_store
from app.services.errors import AppServiceError


class CategoryService:
    def __init__(self, store=None):
        self.store = store or get_metadata_store()

    @staticmethod
    def _require_authenticated(current_user: dict | None) -> None:
        if not isinstance(current_user, dict) or not current_user.get("id"):
            raise AppServiceError(401, "未登录")

    @staticmethod
    def _role_code(current_user: dict | None) -> str:
        return str((current_user or {}).get("role_code") or "")

    @staticmethod
    def _managed_department_ids(current_user: dict | None) -> set[str]:
        managed_ids = (current_user or {}).get("managed_department_ids") or []
        return {str(department_id) for department_id in managed_ids if department_id}

    def _assert_manage_scope(
        self,
        *,
        scope_type: str,
        department_id: str | None,
        current_user: dict | None,
    ) -> None:
        role_code = self._role_code(current_user)
        if role_code == "system_admin":
            return

        if scope_type == "department" and role_code == "department_admin":
            normalized_department_id = str(department_id or "").strip()
            if not normalized_department_id:
                raise AppServiceError(2001, "department_id 不能为空")
            if normalized_department_id not in self._managed_department_ids(current_user):
                raise AppServiceError(401, "无权限管理该部门分类")
            return

        raise AppServiceError(401, "无权限管理分类")

    def _get_category_or_raise(self, category_id: str) -> dict:
        normalized_category_id = str(category_id or "").strip()
        if not normalized_category_id:
            raise AppServiceError(2001, "category_id 不能为空")
        for category in self.store.list_business_categories():
            if str(category.get("id") or "") == normalized_category_id:
                return category
        raise AppServiceError(1001, f"分类ID: {normalized_category_id}")

    def create_category(self, payload: dict, *, current_user: dict | None) -> dict:
        self._require_authenticated(current_user)

        name = str((payload or {}).get("name") or "").strip()
        scope_type = str((payload or {}).get("scope_type") or "").strip()
        department_id = (payload or {}).get("department_id")
        if department_id is not None:
            department_id = str(department_id).strip() or None
        sort_order = int((payload or {}).get("sort_order") or 0)
        status = str((payload or {}).get("status") or "enabled")

        if not name:
            raise AppServiceError(2001, "分类名称不能为空")
        if scope_type not in {"system", "department"}:
            raise AppServiceError(2001, "scope_type 非法")

        self._assert_manage_scope(
            scope_type=scope_type,
            department_id=department_id,
            current_user=current_user,
        )

        if scope_type == "system":
            department_id = None
        elif not department_id:
            raise AppServiceError(2001, "department_id 不能为空")

        return self.store.upsert_business_category(
            {
                "id": (payload or {}).get("id"),
                "name": name,
                "scope_type": scope_type,
                "department_id": department_id,
                "status": status,
                "sort_order": sort_order,
                "created_by": str((current_user or {}).get("id")),
            }
        )

    def create_system_category(self, payload: dict, *, current_user: dict | None) -> dict:
        return self.create_category(
            {**(payload or {}), "scope_type": "system", "department_id": None},
            current_user=current_user,
        )

    def create_department_category(
        self,
        department_id: str,
        payload: dict,
        *,
        current_user: dict | None,
    ) -> dict:
        return self.create_category(
            {
                **(payload or {}),
                "scope_type": "department",
                "department_id": str(department_id or "").strip(),
            },
            current_user=current_user,
        )

    def list_categories(
        self,
        *,
        scope_type: str | None = None,
        department_id: str | None = None,
        current_user: dict | None,
        status: str | None = None,
    ) -> list[dict]:
        self._require_authenticated(current_user)
        normalized_scope_type = str(scope_type).strip() if scope_type else None
        normalized_department_id = str(department_id).strip() if department_id else None
        categories = self.store.list_business_categories(
            scope_type=normalized_scope_type,
            department_id=normalized_department_id,
        )
        if status:
            normalized_status = str(status).strip()
            categories = [
                item
                for item in categories
                if str(item.get("status") or "") == normalized_status
            ]
        return categories

    def list_system_categories(
        self,
        *,
        status: str | None = None,
        current_user: dict | None,
    ) -> list[dict]:
        return self.list_categories(
            scope_type="system",
            department_id=None,
            current_user=current_user,
            status=status,
        )

    def list_department_categories(
        self,
        department_id: str,
        *,
        status: str | None = None,
        current_user: dict | None,
    ) -> list[dict]:
        return self.list_categories(
            scope_type="department",
            department_id=str(department_id or "").strip(),
            current_user=current_user,
            status=status,
        )

    def update_category(
        self,
        category_id: str,
        payload: dict,
        *,
        current_user: dict | None,
    ) -> dict:
        self._require_authenticated(current_user)
        existing = self._get_category_or_raise(category_id)

        merged_scope_type = str((payload or {}).get("scope_type") or existing.get("scope_type") or "").strip()
        merged_department_id = (payload or {}).get("department_id", existing.get("department_id"))
        if merged_department_id is not None:
            merged_department_id = str(merged_department_id).strip() or None
        if merged_scope_type not in {"system", "department"}:
            raise AppServiceError(2001, "scope_type 非法")

        self._assert_manage_scope(
            scope_type=merged_scope_type,
            department_id=merged_department_id,
            current_user=current_user,
        )

        merged_name = str((payload or {}).get("name") or existing.get("name") or "").strip()
        if not merged_name:
            raise AppServiceError(2001, "分类名称不能为空")

        merged_status = str((payload or {}).get("status") or existing.get("status") or "enabled")
        merged_sort_order = int((payload or {}).get("sort_order", existing.get("sort_order", 0)) or 0)
        merged_created_by = str(existing.get("created_by") or (current_user or {}).get("id") or "")

        return self.store.upsert_business_category(
            {
                "id": existing["id"],
                "name": merged_name,
                "scope_type": merged_scope_type,
                "department_id": merged_department_id if merged_scope_type == "department" else None,
                "status": merged_status,
                "sort_order": merged_sort_order,
                "created_by": merged_created_by,
            }
        )


category_service = CategoryService()
