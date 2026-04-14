from typing import List, Optional

from pydantic import BaseModel, Field


class ReaderMatchRange(BaseModel):
    start: int
    end: int
    term: str


class ReaderBlock(BaseModel):
    block_id: str
    block_index: int
    block_type: str = "paragraph"
    heading_path: List[str] = Field(default_factory=list)
    text: str
    page_number: Optional[int] = None
    matches: List[ReaderMatchRange] = Field(default_factory=list)


class ReaderAnchor(BaseModel):
    block_id: Optional[str] = None
    block_index: int = 0
    match_index: int = 0
    start: int = 0
    end: int = 0
    term: Optional[str] = None


class DocumentReaderPayload(BaseModel):
    document_id: str
    filename: str
    file_type: str = ""
    classification_result: Optional[str] = None
    created_at_iso: Optional[str] = None
    parser_name: Optional[str] = None
    extraction_status: Optional[str] = None
    query: str = ""
    keywords: List[str] = Field(default_factory=list)
    total_matches: int = 0
    best_anchor: ReaderAnchor = Field(default_factory=ReaderAnchor)
    blocks: List[ReaderBlock] = Field(default_factory=list)
