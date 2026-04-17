"""Schema - 数据模型"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


# ============ QA Schema ============
class Citation(BaseModel):
    """引用"""
    doc_id: str
    section: Optional[str] = None
    excerpt: Optional[str] = None


class QARequest(BaseModel):
    """问答请求"""
    query: str
    doc_ids: Optional[List[str]] = None
    top_k: int = 8
    session_id: Optional[str] = None


class QAResponse(BaseModel):
    """问答响应"""
    query: str
    answer: str
    citations: List[Citation] = []
    confidence: float = 0.5
    tokens_used: Optional[int] = None
    session_id: Optional[str] = None


class QASession(BaseModel):
    """问答会话"""
    id: str
    query: str
    answer: str
    doc_ids: List[str]
    citations: List[Citation]
    created_at: str


# ============ Topic Schema ============
class KGNode(BaseModel):
    """知识图谱节点"""
    id: str
    label: str
    title: Optional[str] = None
    type: str = "entity"


class KGEdge(BaseModel):
    """知识图谱边"""
    id: str
    from_node: str
    to_node: str
    label: str
    doc_id: Optional[str] = None


class GraphData(BaseModel):
    """图数据"""
    nodes: List[KGNode]
    edges: List[KGEdge]
    stats: Dict[str, Any] = {}


class Entity(BaseModel):
    """实体"""
    text: str
    type: str
    context: Optional[str] = None


class Triple(BaseModel):
    """知识图谱三元组"""
    subject: str
    predicate: str
    object: str
    doc_id: Optional[str] = None
    confidence: float = 1.0
