from app.infra.metadata_store import get_metadata_store


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


audit_service = AuditService()
