from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ClassificationRequest(BaseModel):
    document_id: str


class ClassificationResponse(BaseModel):
    document_id: str
    filename: str
    categories: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    suggested_folders: List[str] = Field(default_factory=list)
    topic_id: Optional[str] = None
    topic_label: Optional[str] = None
    topic_path: List[str] = Field(default_factory=list)
    classification_source: str = "topic_tree"
    old_classification: Optional[str] = None
    new_classification: Optional[str] = None


class CategoryListResponse(BaseModel):
    categories: List[str] = Field(default_factory=list)
    document_count: Dict[str, int] = Field(default_factory=dict)


class CategoryDocument(BaseModel):
    id: Optional[str] = None
    document_id: Optional[str] = None
    filename: str = ""
    file_type: str = ""
    classification_result: Optional[str] = None
    topic_path: List[str] = Field(default_factory=list)
    created_at_iso: Optional[str] = None
    excerpt: str = ""
    keywords: List[str] = Field(default_factory=list)


class CategoryDocumentsResponse(BaseModel):
    category: str
    topic_id: Optional[str] = None
    topic_path: List[str] = Field(default_factory=list)
    total: int = 0
    documents: List[CategoryDocument] = Field(default_factory=list)


class MultiLevelClassificationRequest(BaseModel):
    force_rebuild: bool = False


class TopicTreeBuildRequest(BaseModel):
    force_rebuild: bool = False


class ClassificationTableGenerateRequest(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    persist: bool = True


class ClassificationTableListRequest(BaseModel):
    limit: int = 50
