from typing import Any, Mapping


def _normalize_shared_department_ids(raw_ids: Any) -> list[str]:
    if not isinstance(raw_ids, (list, tuple, set)):
        return []

    normalized: list[str] = []
    for department_id in raw_ids:
        value = str(department_id).strip() if department_id is not None else ""
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_boolean(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def normalize_document_governance(
    payload: Mapping[str, Any] | None,
    current_user: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(payload or {})

    owner_department_id = normalized.get("owner_department_id")
    if not owner_department_id and isinstance(current_user, Mapping):
        owner_department_id = (
            current_user.get("primary_department_id")
            or current_user.get("department_id")
        )

    visibility_scope = str(normalized.get("visibility_scope") or "department")
    shared_department_ids = _normalize_shared_department_ids(normalized.get("shared_department_ids"))
    role_restriction = normalized.get("role_restriction")
    derived_is_public_restricted = visibility_scope == "public" and bool(shared_department_ids or role_restriction)

    normalized["visibility_scope"] = visibility_scope
    normalized["owner_department_id"] = str(owner_department_id) if owner_department_id else None
    normalized["shared_department_ids"] = shared_department_ids
    normalized["business_category_id"] = normalized.get("business_category_id") or "cat-pending"
    normalized["role_restriction"] = role_restriction
    if "is_public_restricted" in normalized and normalized.get("is_public_restricted") is not None:
        normalized["is_public_restricted"] = _normalize_boolean(
            normalized.get("is_public_restricted"),
            default=derived_is_public_restricted,
        )
    else:
        normalized["is_public_restricted"] = derived_is_public_restricted
    normalized["confidentiality_level"] = str(normalized.get("confidentiality_level") or "internal")
    normalized["document_status"] = str(normalized.get("document_status") or "draft")

    return normalized
