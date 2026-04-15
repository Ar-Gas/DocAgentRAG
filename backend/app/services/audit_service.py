import json

from app.infra.metadata_store import get_metadata_store
from app.services.errors import AppServiceError


class AuditService:
    def __init__(self, store=None):
        self.store = store or get_metadata_store()

    def record(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str,
        result: str,
        user: dict | None = None,
        ip_address: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        actor = user or {}
        payload = {
            "user_id": actor.get("id"),
            "username_snapshot": actor.get("username"),
            "department_id": actor.get("primary_department_id"),
            "role_code": actor.get("role_code"),
            "action_type": action_type,
            "target_type": target_type,
            "target_id": target_id,
            "result": result,
            "ip_address": ip_address,
            "metadata_json": metadata or {},
        }
        return self.store.insert_audit_log(payload)

    def _ensure_list_permission(self, current_user: dict | None) -> None:
        role_code = str((current_user or {}).get("role_code") or "")
        if role_code not in {"system_admin", "audit_readonly"}:
            raise AppServiceError(401, "无权限查看审计日志")

    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        action_type: str | None = None,
        result: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        user_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        current_user: dict | None = None,
    ) -> dict:
        self._ensure_list_permission(current_user)

        safe_page = max(int(page or 1), 1)
        safe_page_size = max(int(page_size or 20), 1)
        where_clauses: list[str] = []
        params: list[object] = []

        if action_type:
            where_clauses.append("action_type = ?")
            params.append(action_type)
        if result:
            where_clauses.append("result = ?")
            params.append(result)
        if target_type:
            where_clauses.append("target_type = ?")
            params.append(target_type)
        if target_id:
            where_clauses.append("target_id = ?")
            params.append(target_id)
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)
        if start_time:
            where_clauses.append("created_at >= ?")
            params.append(start_time)
        if end_time:
            where_clauses.append("created_at <= ?")
            params.append(end_time)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        with self.store._connect() as connection:
            count_row = connection.execute(
                f"SELECT COUNT(*) AS count FROM audit_logs {where_sql}",
                tuple(params),
            ).fetchone()
            total = int(count_row["count"]) if count_row else 0

            rows = connection.execute(
                f"""
                SELECT *
                FROM audit_logs
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [safe_page_size, (safe_page - 1) * safe_page_size]),
            ).fetchall()

        items = []
        for row in rows:
            row_dict = dict(row)
            row_dict["metadata_json"] = json.loads(row_dict.get("metadata_json") or "{}")
            items.append(row_dict)

        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": (total + safe_page_size - 1) // safe_page_size if safe_page_size else 0,
        }


audit_service = AuditService()
