from app.core.document_governance import normalize_document_governance
from app.schemas.directory_workspace import (
    DirectoryBreadcrumb,
    DirectoryDocument,
    DirectoryNode,
    DirectoryScope,
    DirectorySearchScope,
    DirectoryWorkspaceResponse,
)
from app.services.authorization_service import authorization_service
from app.services.category_service import category_service
from app.services.errors import AppServiceError
from app.services.organization_service import organization_service
from utils.storage import get_all_documents


class DirectoryService:
    def __init__(self):
        self.authorization_service = authorization_service
        self.organization_service = organization_service
        self.category_service = category_service

    @staticmethod
    def _require_authenticated(current_user: dict | None) -> None:
        if not isinstance(current_user, dict) or not current_user.get("id"):
            raise AppServiceError(401, "未登录")

    @staticmethod
    def _normalize_optional_id(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _workspace_categories(
        categories: list[dict],
        *,
        visible_category_ids: set[str],
    ) -> list[dict]:
        return [
            item
            for item in categories or []
            if str(item.get("status") or "enabled") == "enabled"
            or str(item.get("id") or "") in visible_category_ids
        ]

    @staticmethod
    def _visible_category_ids(
        documents: list[dict],
        *,
        visible_document_ids: set[str],
    ) -> set[str]:
        category_ids: set[str] = set()
        for document in documents:
            document_id = str(document.get("id") or "")
            category_id = str(document.get("business_category_id") or "")
            if document_id and document_id in visible_document_ids and category_id:
                category_ids.add(category_id)
        return category_ids

    @staticmethod
    def _scope_key(
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
    ) -> str:
        if not visibility_scope:
            return "root"

        parts = [visibility_scope]
        if department_id:
            parts.append(department_id)
        if business_category_id:
            parts.append(business_category_id)
        return ":".join(parts)

    @staticmethod
    def _is_system_admin(current_user: dict | None) -> bool:
        return str((current_user or {}).get("role_code") or "") == "system_admin"

    def _validate_scope(
        self,
        *,
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
        accessible_department_ids: set[str],
        department_map: dict[str, dict],
        category_map: dict[str, dict],
        current_user: dict | None,
    ) -> tuple[str | None, str | None, str | None]:
        normalized_visibility_scope = self._normalize_optional_id(visibility_scope)
        normalized_department_id = self._normalize_optional_id(department_id)
        normalized_business_category_id = self._normalize_optional_id(business_category_id)

        if normalized_visibility_scope not in {None, "public", "department"}:
            raise AppServiceError(2001, "visibility_scope 非法")
        if normalized_visibility_scope != "department" and normalized_department_id:
            raise AppServiceError(2001, "department_id 仅适用于部门目录")
        if normalized_visibility_scope is None and normalized_business_category_id:
            raise AppServiceError(2001, "business_category_id 需要目录范围")
        if normalized_business_category_id and normalized_visibility_scope == "department" and not normalized_department_id:
            raise AppServiceError(2001, "department_id 不能为空")
        if normalized_department_id and normalized_department_id not in department_map:
            raise AppServiceError(1001, f"部门ID: {normalized_department_id}")
        if normalized_business_category_id and normalized_business_category_id not in category_map:
            raise AppServiceError(1001, f"分类ID: {normalized_business_category_id}")

        if (
            normalized_visibility_scope == "department"
            and normalized_department_id
            and not self._is_system_admin(current_user)
            and normalized_department_id not in accessible_department_ids
        ):
            raise AppServiceError(401, "无权限查看该部门目录")

        category = category_map.get(normalized_business_category_id) if normalized_business_category_id else None
        if category and normalized_visibility_scope == "public":
            if str(category.get("scope_type") or "") != "system":
                raise AppServiceError(2001, "business_category_id 不属于公共目录")
        if category and normalized_visibility_scope == "department":
            if str(category.get("scope_type") or "") != "department":
                raise AppServiceError(2001, "business_category_id 不属于部门目录")
            expected_department_id = self._normalize_optional_id(category.get("department_id"))
            if expected_department_id != normalized_department_id:
                raise AppServiceError(2001, "business_category_id 不属于该部门")

        return (
            normalized_visibility_scope,
            normalized_department_id,
            normalized_business_category_id,
        )

    @staticmethod
    def _document_department_name(document: dict, department_map: dict[str, dict]) -> str | None:
        department_id = str(document.get("owner_department_id") or "").strip()
        if not department_id:
            return None
        department = department_map.get(department_id) or {}
        return department.get("name")

    @staticmethod
    def _document_category_name(document: dict, category_map: dict[str, dict]) -> str | None:
        category_id = str(document.get("business_category_id") or "").strip()
        if not category_id:
            return None
        category = category_map.get(category_id) or {}
        return category.get("name")

    def _enrich_document(
        self,
        document: dict,
        *,
        department_map: dict[str, dict],
        category_map: dict[str, dict],
    ) -> dict:
        normalized = normalize_document_governance(document or {})
        return {
            **normalized,
            "owner_department_name": self._document_department_name(normalized, department_map),
            "business_category_name": self._document_category_name(normalized, category_map),
        }

    @staticmethod
    def _document_matches_scope(
        document: dict,
        *,
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
    ) -> bool:
        if visibility_scope and str(document.get("visibility_scope") or "") != visibility_scope:
            return False
        if department_id and str(document.get("owner_department_id") or "") != department_id:
            return False
        if business_category_id and str(document.get("business_category_id") or "") != business_category_id:
            return False

        if visibility_scope in {None, "public", "department"} and not business_category_id:
            if visibility_scope is None:
                return False
            if visibility_scope == "public":
                return str(document.get("business_category_id") or "") in {"", "cat-pending"}
            if visibility_scope == "department" and department_id:
                return str(document.get("business_category_id") or "") in {"", "cat-pending"}
            return False

        return True

    def _build_public_tree_node(self, public_categories: list[dict]) -> DirectoryNode:
        children = [
            DirectoryNode(
                node_id=f"public:{category['id']}",
                label=category.get("name") or "",
                folder_type="business_category",
                visibility_scope="public",
                business_category_id=category["id"],
            )
            for category in public_categories
        ]
        return DirectoryNode(
            node_id="public",
            label="公共文档",
            folder_type="visibility",
            visibility_scope="public",
            children=children,
        )

    def _build_department_tree_node(
        self,
        departments: list[dict],
        accessible_department_ids: set[str],
        current_user: dict | None,
    ) -> DirectoryNode:
        is_system_admin = self._is_system_admin(current_user)
        children = [
            DirectoryNode(
                node_id=f"department:{department['id']}",
                label=department.get("name") or "",
                folder_type="department",
                accessible=is_system_admin or department["id"] in accessible_department_ids,
                locked=not (is_system_admin or department["id"] in accessible_department_ids),
                visibility_scope="department",
                department_id=department["id"],
            )
            for department in departments
        ]
        return DirectoryNode(
            node_id="department-root",
            label="部门文档",
            folder_type="visibility",
            visibility_scope="department",
            children=children,
        )

    @staticmethod
    def _department_category_folders(
        *,
        department_id: str,
        department_categories: list[dict],
    ) -> list[DirectoryNode]:
        return [
            DirectoryNode(
                node_id=f"department:{department_id}:{category['id']}",
                label=category.get("name") or "",
                folder_type="business_category",
                visibility_scope="department",
                department_id=department_id,
                business_category_id=category["id"],
            )
            for category in department_categories
            if str(category.get("department_id") or "") == department_id
        ]

    @staticmethod
    def _public_category_folders(public_categories: list[dict]) -> list[DirectoryNode]:
        return [
            DirectoryNode(
                node_id=f"public:{category['id']}",
                label=category.get("name") or "",
                folder_type="business_category",
                visibility_scope="public",
                business_category_id=category["id"],
            )
            for category in public_categories
        ]

    def _current_scope(
        self,
        *,
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
        department_map: dict[str, dict],
        category_map: dict[str, dict],
    ) -> DirectoryScope:
        if not visibility_scope:
            title = "全局目录"
        elif visibility_scope == "public":
            if business_category_id:
                title = str((category_map.get(business_category_id) or {}).get("name") or "公共文档")
            else:
                title = "公共文档"
        elif business_category_id:
            title = str((category_map.get(business_category_id) or {}).get("name") or "部门文档")
        elif department_id:
            title = str((department_map.get(department_id) or {}).get("name") or "部门文档")
        else:
            title = "部门文档"

        return DirectoryScope(
            scope_key=self._scope_key(visibility_scope, department_id, business_category_id),
            title=title,
            visibility_scope=visibility_scope,
            department_id=department_id,
            business_category_id=business_category_id,
        )

    def _breadcrumbs(
        self,
        *,
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
        department_map: dict[str, dict],
        category_map: dict[str, dict],
    ) -> list[DirectoryBreadcrumb]:
        crumbs = [DirectoryBreadcrumb(label="全局目录")]

        if visibility_scope == "public":
            crumbs.append(DirectoryBreadcrumb(label="公共文档", visibility_scope="public"))
            if business_category_id:
                crumbs.append(
                    DirectoryBreadcrumb(
                        label=str((category_map.get(business_category_id) or {}).get("name") or ""),
                        visibility_scope="public",
                        business_category_id=business_category_id,
                    )
                )
        elif visibility_scope == "department":
            crumbs.append(DirectoryBreadcrumb(label="部门文档", visibility_scope="department"))
            if department_id:
                crumbs.append(
                    DirectoryBreadcrumb(
                        label=str((department_map.get(department_id) or {}).get("name") or ""),
                        visibility_scope="department",
                        department_id=department_id,
                    )
                )
            if business_category_id:
                crumbs.append(
                    DirectoryBreadcrumb(
                        label=str((category_map.get(business_category_id) or {}).get("name") or ""),
                        visibility_scope="department",
                        department_id=department_id,
                        business_category_id=business_category_id,
                    )
                )

        return crumbs

    def _folders(
        self,
        *,
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
        tree: list[DirectoryNode],
        public_categories: list[dict],
        department_categories: list[dict],
    ) -> list[DirectoryNode]:
        if not visibility_scope:
            return [
                DirectoryNode(
                    node_id=node.node_id,
                    label=node.label,
                    folder_type=node.folder_type,
                    accessible=node.accessible,
                    locked=node.locked,
                    visibility_scope=node.visibility_scope,
                    department_id=node.department_id,
                    business_category_id=node.business_category_id,
                )
                for node in tree
            ]

        if visibility_scope == "public" and not business_category_id:
            return self._public_category_folders(public_categories)

        if visibility_scope == "department" and not department_id:
            return [child.model_copy(deep=True) for child in tree[1].children]

        if visibility_scope == "department" and department_id and not business_category_id:
            return self._department_category_folders(
                department_id=department_id,
                department_categories=department_categories,
            )

        return []

    @staticmethod
    def _documents(
        documents: list[dict],
        *,
        visible_document_ids: set[str],
        visibility_scope: str | None,
        department_id: str | None,
        business_category_id: str | None,
    ) -> list[DirectoryDocument]:
        results: list[DirectoryDocument] = []
        for document in documents:
            document_id = str(document.get("id") or "")
            if not document_id or document_id not in visible_document_ids:
                continue
            if not DirectoryService._document_matches_scope(
                document,
                visibility_scope=visibility_scope,
                department_id=department_id,
                business_category_id=business_category_id,
            ):
                continue
            results.append(
                DirectoryDocument(
                    id=document.get("id"),
                    filename=document.get("filename") or "",
                    file_type=document.get("file_type") or "",
                    created_at_iso=document.get("created_at_iso"),
                    file_available=bool(document.get("file_available", False)),
                    visibility_scope=str(document.get("visibility_scope") or "department"),
                    owner_department_id=document.get("owner_department_id"),
                    owner_department_name=document.get("owner_department_name"),
                    shared_department_ids=list(document.get("shared_department_ids") or []),
                    business_category_id=document.get("business_category_id"),
                    business_category_name=document.get("business_category_name"),
                    confidentiality_level=str(document.get("confidentiality_level") or "internal"),
                    document_status=str(document.get("document_status") or "draft"),
                )
            )
        return results

    def build_workspace(
        self,
        *,
        visibility_scope: str | None = None,
        department_id: str | None = None,
        business_category_id: str | None = None,
        current_user: dict | None,
    ) -> dict:
        self._require_authenticated(current_user)

        departments = self.organization_service.list_departments(current_user=current_user)
        accessible_department_ids = self.authorization_service._user_department_ids(current_user)
        department_map = {
            str(item.get("id") or ""): item
            for item in departments
            if item.get("id")
        }

        all_public_categories = self.category_service.store.list_business_categories(scope_type="system")
        all_department_categories = self.category_service.store.list_business_categories(scope_type="department")
        all_category_map = {
            str(item.get("id") or ""): item
            for item in [*all_public_categories, *all_department_categories]
            if item.get("id")
        }

        documents = [
            self._enrich_document(
                document,
                department_map=department_map,
                category_map=all_category_map,
            )
            for document in get_all_documents()
        ]
        visible_document_ids = self.authorization_service.list_visible_document_ids(current_user, documents)
        visible_category_ids = self._visible_category_ids(
            documents,
            visible_document_ids=visible_document_ids,
        )
        public_categories = self._workspace_categories(
            all_public_categories,
            visible_category_ids=visible_category_ids,
        )
        department_categories = self._workspace_categories(
            all_department_categories,
            visible_category_ids=visible_category_ids,
        )
        workspace_category_map = {
            str(item.get("id") or ""): item
            for item in [*public_categories, *department_categories]
            if item.get("id")
        }

        normalized_visibility_scope, normalized_department_id, normalized_business_category_id = self._validate_scope(
            visibility_scope=visibility_scope,
            department_id=department_id,
            business_category_id=business_category_id,
            accessible_department_ids=accessible_department_ids,
            department_map=department_map,
            category_map=workspace_category_map,
            current_user=current_user,
        )

        tree = [
            self._build_public_tree_node(public_categories),
            self._build_department_tree_node(departments, accessible_department_ids, current_user),
        ]
        current_scope = self._current_scope(
            visibility_scope=normalized_visibility_scope,
            department_id=normalized_department_id,
            business_category_id=normalized_business_category_id,
            department_map=department_map,
            category_map=workspace_category_map,
        )
        response = DirectoryWorkspaceResponse(
            current_scope=current_scope,
            breadcrumbs=self._breadcrumbs(
                visibility_scope=normalized_visibility_scope,
                department_id=normalized_department_id,
                business_category_id=normalized_business_category_id,
                department_map=department_map,
                category_map=workspace_category_map,
            ),
            tree=tree,
            folders=self._folders(
                visibility_scope=normalized_visibility_scope,
                department_id=normalized_department_id,
                business_category_id=normalized_business_category_id,
                tree=tree,
                public_categories=public_categories,
                department_categories=department_categories,
            ),
            documents=self._documents(
                documents,
                visible_document_ids=visible_document_ids,
                visibility_scope=normalized_visibility_scope,
                department_id=normalized_department_id,
                business_category_id=normalized_business_category_id,
            ),
            search_scope=DirectorySearchScope(
                visibility_scope=normalized_visibility_scope,
                department_id=normalized_department_id,
                business_category_id=normalized_business_category_id,
            ),
        )
        return response.model_dump()
