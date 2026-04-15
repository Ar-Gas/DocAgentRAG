from app.infra.metadata_store import get_metadata_store
from app.services.auth_service import AuthService
from app.services.errors import AppServiceError


class OrganizationService:
    def __init__(self, store=None, auth_service: AuthService | None = None):
        self.store = store or get_metadata_store()
        self.auth_service = auth_service or AuthService(store=self.store)

    @staticmethod
    def _require_authenticated(current_user: dict | None) -> None:
        if not isinstance(current_user, dict) or not current_user.get("id"):
            raise AppServiceError(401, "未登录")

    def _require_system_admin(self, current_user: dict | None) -> None:
        self._require_authenticated(current_user)
        if str((current_user or {}).get("role_code") or "") != "system_admin":
            raise AppServiceError(401, "无权限管理用户")

    @staticmethod
    def _normalize_department_memberships(
        primary_department_id: str,
        collaborative_department_ids: list[str] | None,
    ) -> tuple[str, list[str]]:
        normalized_primary_department_id = str(primary_department_id or "").strip()
        if not normalized_primary_department_id:
            raise AppServiceError(2001, "primary_department_id 不能为空")

        normalized_collaborative_ids: list[str] = []
        seen_ids: set[str] = {normalized_primary_department_id}
        for raw_department_id in collaborative_department_ids or []:
            department_id = str(raw_department_id or "").strip()
            if not department_id or department_id in seen_ids:
                continue
            seen_ids.add(department_id)
            normalized_collaborative_ids.append(department_id)

        return normalized_primary_department_id, normalized_collaborative_ids

    def create_user(self, payload: dict, *, current_user: dict | None) -> dict:
        self._require_system_admin(current_user)

        username = str((payload or {}).get("username") or "").strip()
        password = str((payload or {}).get("password") or "")
        display_name = str((payload or {}).get("display_name") or "").strip()
        role_code = str((payload or {}).get("role_code") or "").strip()
        if not username or not password or not display_name or not role_code:
            raise AppServiceError(2001, "用户字段不完整")

        primary_department_id, collaborative_department_ids = self._normalize_department_memberships(
            str((payload or {}).get("primary_department_id") or ""),
            (payload or {}).get("collaborative_department_ids"),
        )

        user = self.store.upsert_user(
            {
                "id": (payload or {}).get("id"),
                "username": username,
                "password_hash": self.auth_service.hash_password(password),
                "display_name": display_name,
                "status": str((payload or {}).get("status") or "enabled"),
                "primary_department_id": primary_department_id,
                "role_code": role_code,
            }
        )
        self.store.replace_user_department_memberships(
            user["id"],
            primary_department_id,
            collaborative_department_ids,
        )
        return {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "status": user.get("status", "enabled"),
            "primary_department_id": primary_department_id,
            "collaborative_department_ids": collaborative_department_ids,
            "role_code": user["role_code"],
        }

    def list_users(self, page: int, page_size: int, *, current_user: dict | None) -> dict:
        self._require_system_admin(current_user)
        safe_page = max(int(page or 1), 1)
        safe_page_size = max(int(page_size or 10), 1)
        offset = (safe_page - 1) * safe_page_size

        with self.store._connect() as connection:
            count_row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
            total = int(count_row["count"]) if count_row else 0
            rows = connection.execute(
                """
                SELECT
                    id, username, display_name, status, primary_department_id,
                    role_code, last_login_at, created_at, updated_at
                FROM users
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (safe_page_size, offset),
            ).fetchall()

        items: list[dict] = []
        for row in rows:
            user = dict(row)
            memberships = self.store.list_user_department_memberships(user["id"])
            collaborative_department_ids = [
                str(item.get("department_id"))
                for item in memberships
                if item.get("membership_type") == "collaborative" and item.get("department_id")
            ]
            items.append(
                {
                    **user,
                    "collaborative_department_ids": collaborative_department_ids,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": (total + safe_page_size - 1) // safe_page_size if safe_page_size else 0,
        }

    def list_departments(self, *, current_user: dict | None) -> list[dict]:
        self._require_authenticated(current_user)
        return self.store.list_departments()

    def list_roles(self, *, current_user: dict | None) -> list[dict]:
        self._require_authenticated(current_user)
        return self.store.list_roles()


organization_service = OrganizationService()
