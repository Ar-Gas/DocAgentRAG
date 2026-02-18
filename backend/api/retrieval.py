from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict
from pydantic import BaseModel
from utils.retriever import (
    search_documents,
    batch_search_documents,
    get_document_by_id,
    get_document_stats
)

router = APIRouter()

# 响应模型
class SearchResult(BaseModel):
    document_id: str
    filename: str
    path: str
    file_type: str
    similarity: float
    content_snippet: str
    chunk_index: int

class BatchSearchRequest(BaseModel):
    queries: List[str]
    limit: int = 5

class StatsResponse(BaseModel):
    total_chunks: int
    file_types: Dict[str, int]

@router.get("/search", summary="单查询语义检索", response_model=List[SearchResult])
async def search_document_api(
    query: str = Query(..., description="检索关键词/句子"),
    limit: int = Query(10, ge=1, le=100, description="返回结果数量")
):
    """
    对文档库进行语义检索，返回最相关的文档片段
    """
    results = search_documents(query, limit=limit)
    if not results:
        return []
    return results

@router.post("/batch-search", summary="批量查询语义检索")
async def batch_search_document_api(request: BatchSearchRequest):
    """
    批量执行多个查询的语义检索
    """
    results = batch_search_documents(request.queries, limit=request.limit)
    return {
        "queries": request.queries,
        "results": results
    }

@router.get("/document/{document_id}", summary="根据ID获取文档全部分片")
async def get_document_chunks(document_id: str):
    """
    根据文档ID，获取该文档的所有文本分片和元数据
    """
    result = get_document_by_id(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return result

@router.get("/stats", summary="获取文档库统计信息", response_model=StatsResponse)
async def get_document_stats_api():
    """
    获取文档库的统计信息，包括总分片数、文件类型分布
    """
    stats = get_document_stats()
    return stats