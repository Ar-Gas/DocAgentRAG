from typing import Iterable


class AuthorizationService:
    def _user_role(self, user: dict | None) -> str:
        if not isinstance(user, dict):
            return ""
        return str(user.get("role_code") or "")

    def _user_department_ids(self, user: dict | None) -> set[str]:
        if not isinstance(user, dict):
            return set()

        department_ids: set[str] = set()
        raw_department_ids = user.get("department_ids") or []
        if isinstance(raw_department_ids, (list, tuple, set)):
            for department_id in raw_department_ids:
                if department_id:
                    department_ids.add(str(department_id))

        primary_department_id = user.get("primary_department_id")
        if primary_department_id:
            department_ids.add(str(primary_department_id))

        collaborative_department_ids = user.get("collaborative_department_ids") or []
        if isinstance(collaborative_department_ids, (list, tuple, set)):
            for department_id in collaborative_department_ids:
                if department_id:
                    department_ids.add(str(department_id))

        department_id = user.get("department_id")
        if department_id:
            department_ids.add(str(department_id))

        return department_ids

    def _managed_department_ids(self, user: dict | None) -> set[str]:
        if not isinstance(user, dict):
            return set()

        managed_ids = user.get("managed_department_ids") or []
        result: set[str] = set()
        if isinstance(managed_ids, (list, tuple, set)):
            for department_id in managed_ids:
                if department_id:
                    result.add(str(department_id))

        return result or self._user_department_ids(user)

    def _document_shared_department_ids(self, document: dict | None) -> set[str]:
        if not isinstance(document, dict):
            return set()

        shared_ids = document.get("shared_department_ids") or []
        result: set[str] = set()
        if isinstance(shared_ids, (list, tuple, set)):
            for department_id in shared_ids:
                if department_id:
                    result.add(str(department_id))
        return result

    def can_view_document(self, user: dict, document: dict) -> bool:
        if self._user_role(user) == "system_admin":
            return True

        role_restriction = (document or {}).get("role_restriction")
        if role_restriction and str(role_restriction) != self._user_role(user):
            return False

        user_department_ids = self._user_department_ids(user)
        shared_department_ids = self._document_shared_department_ids(document)
        visibility_scope = str((document or {}).get("visibility_scope") or "department")

        if visibility_scope == "public":
            if not shared_department_ids:
                return True
            return bool(user_department_ids & shared_department_ids)

        owner_department_id = (document or {}).get("owner_department_id")
        document_department_ids = set(shared_department_ids)
        if owner_department_id:
            document_department_ids.add(str(owner_department_id))
        return bool(user_department_ids & document_department_ids)

    def can_manage_document(self, user: dict, document: dict) -> bool:
        role_code = self._user_role(user)
        if role_code == "system_admin":
            return True
        if role_code != "department_admin":
            return False

        managed_department_ids = self._managed_department_ids(user)
        document_department_ids = self._document_shared_department_ids(document)
        owner_department_id = (document or {}).get("owner_department_id")
        if owner_department_id:
            document_department_ids.add(str(owner_department_id))
        return bool(managed_department_ids & document_department_ids)

    def list_visible_document_ids(self, user: dict, documents: Iterable[dict]) -> set[str]:
        visible_document_ids: set[str] = set()
        for document in documents or []:
            if self.can_view_document(user, document):
                document_id = (document or {}).get("id")
                if document_id:
                    visible_document_ids.add(str(document_id))
        return visible_document_ids


authorization_service = AuthorizationService()


def can_view_document(user: dict, document: dict) -> bool:
    return authorization_service.can_view_document(user, document)


def can_manage_document(user: dict, document: dict) -> bool:
    return authorization_service.can_manage_document(user, document)


def list_visible_document_ids(user: dict, documents: Iterable[dict]) -> set[str]:
    return authorization_service.list_visible_document_ids(user, documents)
