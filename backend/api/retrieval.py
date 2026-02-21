from fastapi import APIRouter, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from utils.retriever import (
    search_documents,
    batch_search_documents,
    get_document_by_id,
    get_document_stats,
    hybrid_search
)
from utils.smart_retrieval import (
    smart_retrieval,
    expand_query_with_llm,
    expand_query_keywords,
    is_llm_available
)
from api import success, BusinessException

logger = logging.getLogger(__name__)

router = APIRouter()

class BatchSearchRequest(BaseModel):
    queries: List[str]
    limit: int = 5

class HybridSearchRequest(BaseModel):
    query: str
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = True
    file_types: List[str] = None

class SmartSearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_query_expansion: bool = True
    use_llm_rerank: bool = True
    expansion_method: str = 'llm'
    file_types: List[str] = None

def _build_search_result(metadata: dict, snippet: str, distance: float) -> dict:
    content_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
    similarity = max(0.0, min(1.0, 1 - distance))
    
    return {
        "document_id": metadata.get('document_id', metadata.get('id', '')),
        "filename": metadata.get('filename', ''),
        "path": metadata.get('filepath', metadata.get('path', '')),
        "file_type": metadata.get('file_type', ''),
        "similarity": round(similarity, 4),
        "content_snippet": content_snippet,
        "chunk_index": metadata.get('chunk_index', 0)
    }

def _process_search_results(results: dict) -> List[dict]:
    if not results:
        return []
    
    search_results = []
    metadatas_list = results.get('metadatas', [])
    distances_list = results.get('distances', [])
    documents_list = results.get('documents', [])
    
    if not metadatas_list or not distances_list or not documents_list:
        return []
    
    if not isinstance(metadatas_list[0], list):
        metadatas_list = [metadatas_list]
        distances_list = [distances_list]
        documents_list = [documents_list]
    
    for i in range(len(metadatas_list)):
        metadatas = metadatas_list[i] or []
        distances = distances_list[i] or []
        documents = documents_list[i] or []
        
        min_len = min(len(metadatas), len(distances), len(documents))
        for j in range(min_len):
            metadata = metadatas[j]
            distance = distances[j]
            snippet = documents[j]
            
            if metadata is None:
                continue
            
            search_results.append(_build_search_result(metadata, snippet, distance))
    
    search_results.sort(key=lambda x: x['similarity'], reverse=True)
    return search_results

@router.get("/search", summary="单查询语义检索")
async def search_document_api(
    query: str = Query(..., description="检索关键词/句子"),
    limit: int = Query(10, ge=1, le=100, description="返回结果数量"),
    use_rerank: bool = Query(False, description="是否使用重排序提升结果质量"),
    file_types: str = Query(None, description="文件类型过滤，逗号分隔，如 'pdf,docx'")
):
    if not query or not query.strip():
        raise BusinessException(code=3002, detail="查询关键词不能为空")

    file_type_list = None
    if file_types:
        file_type_list = [ft.strip().lstrip('.') for ft in file_types.split(',') if ft.strip()]

    results = search_documents(
        query,
        limit=limit,
        use_rerank=use_rerank,
        file_types=file_type_list
    )

    logger.info(f"语义检索完成: query='{query[:50]}...', results={len(results)}, rerank={use_rerank}, filters={file_type_list}")

    return success(data={
        "query": query,
        "total": len(results),
        "results": results
    })

@router.post("/hybrid-search", summary="混合检索（向量+BM25关键词）")
async def hybrid_search_api(request: HybridSearchRequest):
    """
    混合检索：结合向量语义检索和BM25关键词精确匹配
    - alpha: 向量检索权重 (0-1)，值越大越偏向语义相似
    - use_rerank: 是否使用重排序模型优化结果
    """
    if not request.query or not request.query.strip():
        raise BusinessException(code=3002, detail="查询关键词不能为空")
    
    alpha = max(0.0, min(1.0, request.alpha))
    
    results = hybrid_search(
        query=request.query,
        limit=request.limit,
        alpha=alpha,
        use_rerank=request.use_rerank,
        file_types=request.file_types
    )
    
    logger.info(f"混合检索完成: query='{request.query[:50]}...', alpha={alpha}, results={len(results)}")
    
    return success(data={
        "query": request.query,
        "total": len(results),
        "alpha": alpha,
        "results": results
    })

@router.post("/batch-search", summary="批量查询语义检索")
async def batch_search_document_api(request: BatchSearchRequest):
    if not request.queries or len(request.queries) == 0:
        raise BusinessException(code=3002, detail="查询列表不能为空")
    
    results = batch_search_documents(request.queries, limit=request.limit)
    
    batch_results = []
    for i, query in enumerate(request.queries):
        query_results = results[i] if i < len(results) else []
        batch_results.append({
            "query": query,
            "total": len(query_results),
            "results": query_results
        })
    
    logger.info(f"批量检索完成: queries={len(request.queries)}")
    
    return success(data={
        "total_queries": len(request.queries),
        "batch_results": batch_results
    })

@router.get("/document/{document_id}", summary="根据ID获取文档全部分片")
async def get_document_chunks(document_id: str):
    result = get_document_by_id(document_id)
    if not result:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    chunks = result.get('chunks', [])
    metadatas = result.get('metadatas', [])
    ids = result.get('ids', [])
    
    chunk_list = []
    for i, (chunk, metadata, chunk_id) in enumerate(zip(chunks, metadatas, ids)):
        chunk_list.append({
            "chunk_id": chunk_id,
            "chunk_index": i,
            "content": chunk[:500] + "..." if len(chunk) > 500 else chunk,
            "full_length": len(chunk),
            "metadata": metadata
        })
    
    return success(data={
        "document_id": document_id,
        "total_chunks": len(chunks),
        "chunks": chunk_list
    })

@router.get("/stats", summary="获取文档库统计信息")
async def get_document_stats_api():
    stats = get_document_stats()
    
    return success(data={
        "total_chunks": stats.get('total_chunks', 0),
        "file_types": stats.get('file_types', {})
    })

@router.post("/smart-search", summary="智能检索（查询扩展+多查询+LLM重排序）")
async def smart_search_api(request: SmartSearchRequest):
    """
    智能检索：完整的 RAG 优化流程
    
    流程：
    1. Query Expansion: 使用LLM扩展查询，生成同义词/相关词
    2. Multi-Query Retrieval: 对多个扩展查询并行检索
    3. Result Fusion: 合并检索结果（RRF算法）
    4. LLM Reranking: 使用大模型精确重排序
    
    参数说明：
    - use_query_expansion: 是否启用查询扩展
    - use_llm_rerank: 是否启用LLM重排序
    - expansion_method: 扩展方法 ('llm' 或 'keyword')
    
    需要配置环境变量：
    - OPENAI_API_KEY: API密钥
    - OPENAI_BASE_URL: API地址（默认DeepSeek）
    - LLM_MODEL: 模型名称
    """
    if not request.query or not request.query.strip():
        raise BusinessException(code=3002, detail="查询关键词不能为空")
    
    def search_wrapper(query, limit=10):
        return hybrid_search(
            query=query,
            limit=limit,
            alpha=0.5,
            use_rerank=False,
            file_types=request.file_types
        )
    
    results, meta_info = smart_retrieval(
        query=request.query,
        search_func=search_wrapper,
        limit=request.limit,
        use_query_expansion=request.use_query_expansion,
        use_llm_rerank=request.use_llm_rerank,
        expansion_method=request.expansion_method
    )
    
    logger.info(f"智能检索完成: query='{request.query[:50]}...', "
                f"expansions={len(meta_info['expanded_queries'])}, "
                f"results={len(results)}")
    
    return success(data={
        "query": request.query,
        "total": len(results),
        "results": results,
        "meta": {
            "expanded_queries": meta_info['expanded_queries'],
            "expansion_method": meta_info['expansion_method'],
            "rerank_method": meta_info['rerank_method'],
            "total_candidates": meta_info['total_candidates']
        }
    })

@router.get("/expand-query", summary="查询扩展预览")
async def expand_query_api(
    query: str = Query(..., description="原始查询"),
    method: str = Query('llm', description="扩展方法: llm 或 keyword")
):
    """
    预览查询扩展结果，不执行检索
    用于调试和展示LLM如何扩展查询
    """
    if not query or not query.strip():
        raise BusinessException(code=3002, detail="查询关键词不能为空")
    
    if method == 'llm':
        if not is_llm_available():
            return success(data={
                "query": query,
                "method": "keyword_fallback",
                "expanded_queries": expand_query_keywords(query),
                "llm_available": False
            })
        expanded = expand_query_with_llm(query)
    else:
        expanded = expand_query_keywords(query)
    
    return success(data={
        "query": query,
        "method": method,
        "expanded_queries": expanded,
        "llm_available": is_llm_available()
    })

@router.get("/llm-status", summary="检查LLM服务状态")
async def check_llm_status():
    """检查LLM服务是否可用"""
    import os
    
    return success(data={
        "llm_available": is_llm_available(),
        "api_configured": bool(os.environ.get("OPENAI_API_KEY", "")),
        "base_url": os.environ.get("OPENAI_BASE_URL", "未配置"),
        "model": os.environ.get("LLM_MODEL", "未配置")
    })
