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

        role_code = self._role_code(current_user)
        if role_code == "system_admin":
            pass
        elif scope_type == "department" and role_code == "department_admin":
            if not department_id:
                raise AppServiceError(2001, "department_id 不能为空")
            if department_id not in self._managed_department_ids(current_user):
                raise AppServiceError(401, "无权限管理该部门分类")
        else:
            raise AppServiceError(401, "无权限管理分类")

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

    def list_categories(
        self,
        *,
        scope_type: str | None = None,
        department_id: str | None = None,
        current_user: dict | None,
    ) -> list[dict]:
        self._require_authenticated(current_user)
        normalized_scope_type = str(scope_type).strip() if scope_type else None
        normalized_department_id = str(department_id).strip() if department_id else None
        return self.store.list_business_categories(
            scope_type=normalized_scope_type,
            department_id=normalized_department_id,
        )


category_service = CategoryService()
