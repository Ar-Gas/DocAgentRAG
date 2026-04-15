from pydantic import BaseModel, Field


class DirectoryWorkspaceRequest(BaseModel):
    visibility_scope: str | None = None
    department_id: str | None = None
    business_category_id: str | None = None


class DirectoryScope(BaseModel):
    scope_key: str
    title: str
    visibility_scope: str | None = None
    department_id: str | None = None
    business_category_id: str | None = None


class DirectoryBreadcrumb(BaseModel):
    label: str
    visibility_scope: str | None = None
    department_id: str | None = None
    business_category_id: str | None = None


class DirectoryNode(BaseModel):
    node_id: str
    label: str
    folder_type: str
    accessible: bool = True
    locked: bool = False
    visibility_scope: str | None = None
    department_id: str | None = None
    business_category_id: str | None = None
    children: list["DirectoryNode"] = Field(default_factory=list)


class DirectoryDocument(BaseModel):
    id: str | None = None
    filename: str = ""
    file_type: str = ""
    created_at_iso: str | None = None
    file_available: bool = False
    visibility_scope: str = "department"
    owner_department_id: str | None = None
    owner_department_name: str | None = None
    shared_department_ids: list[str] = Field(default_factory=list)
    business_category_id: str | None = None
    business_category_name: str | None = None
    confidentiality_level: str = "internal"
    document_status: str = "draft"


class DirectorySearchScope(BaseModel):
    visibility_scope: str | None = None
    department_id: str | None = None
    business_category_id: str | None = None


class DirectoryWorkspaceResponse(BaseModel):
    current_scope: DirectoryScope
    breadcrumbs: list[DirectoryBreadcrumb] = Field(default_factory=list)
    tree: list[DirectoryNode] = Field(default_factory=list)
    folders: list[DirectoryNode] = Field(default_factory=list)
    documents: list[DirectoryDocument] = Field(default_factory=list)
    search_scope: DirectorySearchScope
