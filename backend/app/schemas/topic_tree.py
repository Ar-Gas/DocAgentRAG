from typing import List, Optional

from pydantic import BaseModel, Field


class TopicDocument(BaseModel):
    document_id: str
    filename: str
    file_type: str = ""
    classification_result: Optional[str] = None
    created_at_iso: Optional[str] = None
    excerpt: str = ""
    keywords: List[str] = Field(default_factory=list)


class TopicNode(BaseModel):
    topic_id: str
    label: str
    keywords: List[str] = Field(default_factory=list)
    document_count: int = 0
    documents: List[TopicDocument] = Field(default_factory=list)
    children: List["TopicNode"] = Field(default_factory=list)


class TopicTreeResponse(BaseModel):
    schema_version: int = 2
    generated_at: str
    total_documents: int = 0
    clustered_documents: int = 0
    excluded_documents: int = 0
    topic_count: int = 0
    generation_method: str = "doc_embedding_cluster+llm_label"
    topics: List[TopicNode] = Field(default_factory=list)


TopicNode.model_rebuild()
