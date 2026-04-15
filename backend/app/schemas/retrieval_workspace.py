from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceBlock(BaseModel):
    block_id: str
    block_index: int = 0
    block_type: str = "paragraph"
    snippet: str = ""
    heading_path: List[str] = Field(default_factory=list)
    score: float = 0.0
    page_number: Optional[int] = None
    match_reason: str = ""


class DocumentSearchResult(BaseModel):
    document_id: str
    filename: str
    file_type: str = ""
    path: str = ""
    classification_result: Optional[str] = None
    created_at_iso: Optional[str] = None
    parser_name: Optional[str] = None
    extraction_status: Optional[str] = None
    score: float = 0.0
    best_similarity: float = 0.0
    hit_count: int = 0
    result_count: int = 0
    best_excerpt: str = ""
    best_block_id: Optional[str] = None
    matched_terms: List[str] = Field(default_factory=list)
    preview_content: str = ""
    evidence_blocks: List[EvidenceBlock] = Field(default_factory=list)
    top_segments: List[Dict[str, Any]] = Field(default_factory=list)
    results: List[Dict[str, Any]] = Field(default_factory=list)


class WorkspaceSearchResponse(BaseModel):
    query: str = ""
    mode: str = "hybrid"
    total_results: int = 0
    total_documents: int = 0
    results: List[Dict[str, Any]] = Field(default_factory=list)
    documents: List[DocumentSearchResult] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    applied_filters: Dict[str, Any] = Field(default_factory=dict)


class SummaryCitation(BaseModel):
    document_id: Optional[str] = None
    filename: str = ""
    block_id: Optional[str] = None
    block_index: Optional[int] = None
    score: float = 0.0
    snippet: str = ""


class DocumentSummaryResponse(BaseModel):
    summary: str
    citations: List[SummaryCitation] = Field(default_factory=list)
    llm_used: bool = False
