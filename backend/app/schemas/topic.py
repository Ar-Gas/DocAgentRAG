"""Topics Schema - 主题和图谱相关数据模型"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class GraphNode(BaseModel):
    """图节点"""
    id: str
    label: str
    type: str


class GraphEdge(BaseModel):
    """图边"""
    id: str
    source: str
    target: str
    label: str


class GraphVisualization(BaseModel):
    """图可视化数据"""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    stats: Dict[str, Any]
