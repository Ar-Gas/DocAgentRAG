from fastapi import APIRouter, Query, File, UploadFile, Form
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging
import base64
import tempfile
import os

from utils.retriever import (
    search_documents,
    batch_search_documents,
    get_document_by_id,
    get_document_stats,
    hybrid_search,
    multimodal_search,
    hybrid_multimodal_search,
    keyword_search,
    search_with_highlight
)
from utils.smart_retrieval import (
    smart_retrieval,
    smart_multimodal_retrieval,
    expand_query_with_llm,
    expand_query_keywords,
    is_llm_available
)
# from utils.search_engine import get_search_engine
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
    file_types: Optional[List[str]] = None

class SmartSearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_query_expansion: bool = True
    use_llm_rerank: bool = True
    expansion_method: str = 'llm'
    file_types: Optional[List[str]] = None

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
    
    doubao_key = os.environ.get("DOUBAO_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    
    return success(data={
        "llm_available": is_llm_available(),
        "provider": "doubao" if doubao_key else ("openai" if openai_key else None),
        "doubao_configured": bool(doubao_key),
        "doubao_model": os.environ.get("DOUBAO_LLM_MODEL", "doubao-pro-32k-241115"),
        "openai_configured": bool(openai_key),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL", "未配置"),
        "openai_model": os.environ.get("LLM_MODEL", "未配置")
    })


class MultimodalSearchRequest(BaseModel):
    query: str = ""
    image_url: Optional[str] = None
    limit: int = 10
    file_types: Optional[List[str]] = None


class HybridMultimodalSearchRequest(BaseModel):
    query: str = ""
    image_url: Optional[str] = None
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = True
    file_types: Optional[List[str]] = None


@router.post("/multimodal-search", summary="多模态检索（文本+图片）")
async def multimodal_search_api(request: MultimodalSearchRequest):
    """
    多模态检索：支持文本+图片联合查询
    
    使用豆包多模态嵌入API，支持：
    - 纯文本查询
    - 纯图片查询
    - 文本+图片联合查询
    
    参数：
    - query: 查询文本（可选，与image_url至少提供一个）
    - image_url: 图片URL（可选）
    - limit: 返回结果数量
    - file_types: 文件类型过滤
    """
    if not request.query and not request.image_url:
        raise BusinessException(code=3002, detail="查询文本和图片URL至少需要提供一个")
    
    results = multimodal_search(
        query=request.query,
        image_url=request.image_url,
        limit=request.limit,
        file_types=request.file_types
    )
    
    logger.info(f"多模态检索完成: query='{request.query[:50] if request.query else ''}', "
                f"has_image={bool(request.image_url)}, results={len(results)}")
    
    return success(data={
        "query": request.query,
        "has_image": bool(request.image_url),
        "total": len(results),
        "results": results
    })


@router.post("/multimodal-search-upload", summary="多模态检索（上传图片）")
async def multimodal_search_upload_api(
    query: str = Form(default=""),
    image: UploadFile = File(default=None),
    limit: int = Form(default=10),
    file_types: str = Form(default=None)
):
    """
    多模态检索：通过上传图片进行检索
    
    参数：
    - query: 查询文本（可选）
    - image: 上传的图片文件（可选，与query至少提供一个）
    - limit: 返回结果数量
    - file_types: 文件类型过滤，逗号分隔
    """
    if not query and not image:
        raise BusinessException(code=3002, detail="查询文本和图片至少需要提供一个")
    
    file_type_list = None
    if file_types:
        file_type_list = [ft.strip().lstrip('.') for ft in file_types.split(',') if ft.strip()]
    
    image_path = None
    if image:
        try:
            suffix = os.path.splitext(image.filename)[1] if image.filename else '.jpg'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await image.read()
                tmp.write(content)
                image_path = tmp.name
        except Exception as e:
            logger.error(f"保存上传图片失败: {str(e)}")
            raise BusinessException(code=3002, detail=f"图片处理失败: {str(e)}")
    
    try:
        results = multimodal_search(
            query=query,
            image_path=image_path,
            limit=limit,
            file_types=file_type_list
        )
        
        logger.info(f"多模态检索(上传)完成: query='{query[:50] if query else ''}', "
                    f"has_image={bool(image)}, results={len(results)}")
        
        return success(data={
            "query": query,
            "has_image": bool(image),
            "image_filename": image.filename if image else None,
            "total": len(results),
            "results": results
        })
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


class KeywordSearchRequest(BaseModel):
    query: str
    limit: int = 10
    file_types: Optional[List[str]] = None


@router.post("/keyword-search", summary="精确关键词检索（BM25）")
async def keyword_search_api(request: KeywordSearchRequest):
    """
    精确关键词检索：仅使用 BM25 算法进行关键词精确匹配
    
    适用于：
    - 需要精确匹配关键词的场景
    - 文件名搜索
    - 专业术语搜索
    
    不使用向量检索，纯粹基于关键词匹配
    """
    if not request.query or not request.query.strip():
        raise BusinessException(code=3002, detail="查询关键词不能为空")
    
    results = keyword_search(
        query=request.query,
        limit=request.limit,
        file_types=request.file_types
    )
    
    logger.info(f"关键词检索完成: query='{request.query[:50]}...', results={len(results)}")
    
    return success(data={
        "query": request.query,
        "total": len(results),
        "results": results
    })


class SearchWithHighlightRequest(BaseModel):
    query: str
    search_type: str = "hybrid"
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = False
    file_types: Optional[List[str]] = None


@router.post("/search-with-highlight", summary="带关键词高亮的检索")
async def search_with_highlight_api(request: SearchWithHighlightRequest):
    """
    带关键词高亮的检索功能
    
    特点：
    - 自动提取查询中的关键词
    - 在检索结果中高亮匹配的关键词
    - 返回匹配的关键词列表
    
    search_type 选项：
    - keyword: 精确关键词检索
    - vector: 向量语义检索
    - hybrid: 混合检索（向量+关键词）
    - smart: 智能检索（需要LLM）
    """
    if not request.query or not request.query.strip():
        raise BusinessException(code=3002, detail="查询关键词不能为空")
    
    valid_types = ['keyword', 'vector', 'hybrid', 'smart']
    search_type = request.search_type if request.search_type in valid_types else 'hybrid'
    
    results, meta_info = search_with_highlight(
        query=request.query,
        search_type=search_type,
        limit=request.limit,
        alpha=request.alpha,
        use_rerank=request.use_rerank,
        file_types=request.file_types
    )
    
    logger.info(f"带高亮检索完成: query='{request.query[:50]}...', type={search_type}, results={len(results)}")
    
    return success(data={
        "query": request.query,
        "search_type": search_type,
        "total": len(results),
        "keywords": meta_info.get('keywords', []),
        "results": results
    })


@router.get("/search-types", summary="获取支持的检索类型")
async def get_search_types():
    """
    返回系统支持的检索类型列表及其说明
    """
    return success(data={
        "search_types": [
            {
                "type": "keyword",
                "name": "精确关键词检索",
                "description": "仅使用BM25算法进行关键词精确匹配，适合精确查找文件名或专业术语",
                "supports_highlight": True
            },
            {
                "type": "vector",
                "name": "向量语义检索",
                "description": "使用向量嵌入进行语义相似度匹配，适合语义相近的查询",
                "supports_highlight": True
            },
            {
                "type": "hybrid",
                "name": "混合检索",
                "description": "结合向量检索和关键词检索，可调节权重",
                "supports_highlight": True,
                "has_alpha": True
            },
            {
                "type": "smart",
                "name": "智能检索",
                "description": "使用LLM进行查询扩展和多查询融合，需要配置LLM",
                "supports_highlight": True
            }
        ]
    })


@router.post("/hybrid-multimodal-search", summary="混合多模态检索")
async def hybrid_multimodal_search_api(request: HybridMultimodalSearchRequest):
    """
    混合多模态检索：向量检索 + BM25关键词检索，支持图片输入
    
    参数：
    - query: 查询文本（可选，与image_url至少提供一个）
    - image_url: 图片URL（可选）
    - limit: 返回结果数量
    - alpha: 向量检索权重 (0-1)
    - use_rerank: 是否使用重排序
    - file_types: 文件类型过滤
    """
    if not request.query and not request.image_url:
        raise BusinessException(code=3002, detail="查询文本和图片URL至少需要提供一个")
    
    alpha = max(0.0, min(1.0, request.alpha))
    
    results = hybrid_multimodal_search(
        query=request.query,
        image_url=request.image_url,
        limit=request.limit,
        alpha=alpha,
        use_rerank=request.use_rerank,
        file_types=request.file_types
    )
    
    logger.info(f"混合多模态检索完成: query='{request.query[:50] if request.query else ''}', "
                f"has_image={bool(request.image_url)}, alpha={alpha}, results={len(results)}")
    
    return success(data={
        "query": request.query,
        "has_image": bool(request.image_url),
        "total": len(results),
        "alpha": alpha,
        "results": results
    })


@router.post("/smart-multimodal-search", summary="智能多模态检索")
async def smart_multimodal_search_api(
    query: str = Form(default=""),
    image_url: str = Form(default=None),
    image: UploadFile = File(default=None),
    limit: int = Form(default=10),
    use_query_expansion: bool = Form(default=True),
    use_llm_rerank: bool = Form(default=True),
    expansion_method: str = Form(default='llm'),
    file_types: str = Form(default=None)
):
    """
    智能多模态检索：完整的 Query Expansion + Multi-Query Retrieval + LLM Reranking
    
    支持图片URL或上传图片文件
    
    参数：
    - query: 查询文本
    - image_url: 图片URL（可选）
    - image: 上传的图片文件（可选）
    - limit: 返回结果数量
    - use_query_expansion: 是否启用查询扩展
    - use_llm_rerank: 是否启用LLM重排序
    - expansion_method: 扩展方法 ('llm' 或 'keyword')
    - file_types: 文件类型过滤，逗号分隔
    """
    if not query and not image_url and not image:
        raise BusinessException(code=3002, detail="查询文本、图片URL和上传图片至少需要提供一个")
    
    file_type_list = None
    if file_types:
        file_type_list = [ft.strip().lstrip('.') for ft in file_types.split(',') if ft.strip()]
    
    image_path = None
    if image:
        try:
            suffix = os.path.splitext(image.filename)[1] if image.filename else '.jpg'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await image.read()
                tmp.write(content)
                image_path = tmp.name
        except Exception as e:
            logger.error(f"保存上传图片失败: {str(e)}")
            raise BusinessException(code=3002, detail=f"图片处理失败: {str(e)}")
    
    try:
        def search_wrapper(q, limit=10):
            return hybrid_multimodal_search(
                query=q,
                image_url=image_url,
                image_path=image_path,
                limit=limit,
                alpha=0.5,
                use_rerank=False,
                file_types=file_type_list
            )
        
        results, meta_info = smart_multimodal_retrieval(
            query=query,
            search_func=search_wrapper,
            limit=limit,
            image_url=image_url,
            image_path=image_path,
            use_query_expansion=use_query_expansion,
            use_llm_rerank=use_llm_rerank,
            expansion_method=expansion_method
        )
        
        logger.info(f"智能多模态检索完成: query='{query[:50] if query else ''}', "
                    f"has_image={bool(image_url or image)}, results={len(results)}")
        
        return success(data={
            "query": query,
            "has_image": bool(image_url or image),
            "total": len(results),
            "results": results,
            "meta": {
                "expanded_queries": meta_info.get('expanded_queries', [query]),
                "expansion_method": meta_info.get('expansion_method'),
                "rerank_method": meta_info.get('rerank_method'),
                "total_candidates": meta_info.get('total_candidates', 0)
            }
        })
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)


# class UnifiedSearchRequest(BaseModel):
#     """统一检索请求"""
#     query: str
#     search_type: str = "hybrid"
#     limit: int = 10
#     alpha: float = 0.5
#     use_rerank: bool = False
#     file_types: Optional[List[str]] = None
#     image_url: Optional[str] = None
#
#
# @router.post("/unified-search", summary="统一检索入口（推荐）")
# async def unified_search_api(request: UnifiedSearchRequest):
#     """
#     统一检索入口 - 支持百度式检索语法
#     
#     支持的检索语法：
#     - 关键词 : 模糊匹配
#     - \"精确短语\" : 精确匹配（双引号包裹）
#     - -排除词 : 排除指定词
#     - filetype:pdf : 文件类型过滤
#     
#     检索类型：
#     - keyword: 精确关键词检索（BM25）
#     - vector: 向量语义检索
#     - hybrid: 混合检索（默认）
#     - smart: 智能检索（LLM增强）
#     - multimodal: 多模态检索
#     
#     示例：
#     - 简单查询: {"query": "项目报告", "search_type": "hybrid"}
#     - 精确匹配: {"query": "\"2024年度报告\"", "search_type": "keyword"}
#     - 高级查询: {"query": "项目报告 -草稿 filetype:pdf", "search_type": "hybrid"}
#     """
#     if not request.query or not request.query.strip():
#         raise BusinessException(code=3002, detail="查询关键词不能为空")
#     
#     valid_search_types = ['keyword', 'vector', 'hybrid', 'smart', 'multimodal']
#     search_type = request.search_type if request.search_type in valid_search_types else 'hybrid'
#     
#     engine = get_search_engine()
#     results, meta_info = engine.search(
#         query=request.query,
#         search_type=search_type,
#         limit=request.limit,
#         alpha=request.alpha,
#         use_rerank=request.use_rerank,
#         file_types=request.file_types,
#         image_url=request.image_url
#     )
#     
#     logger.info(f"统一检索完成: type={search_type}, query='{request.query[:50]}...', results={len(results)}")
#     
#     return success(data={
#         "query": request.query,
#         "search_type": search_type,
#         "total": len(results),
#         "results": results,
#         "meta": meta_info
#     })
#
#
# @router.get("/search-syntax-help", summary="检索语法帮助")
# async def get_search_syntax_help():
#     """获取检索语法帮助文档"""
#     return success(data={
#         "syntax_examples": [
#             {
#                 "pattern": "关键词",
#                 "description": "模糊匹配，包含该关键词的文档",
#                 "example": "项目报告"
#             },
#             {
#                 "pattern": "\"精确短语\"",
#                 "description": "精确匹配，必须包含完整短语",
#                 "example": "\"2024年度总结\""
#             },
#             {
#                 "pattern": "-排除词",
#                 "description": "排除包含该词的文档",
#                 "example": "项目报告 -草稿"
#             },
#             {
#                 "pattern": "filetype:扩展名",
#                 "description": "只搜索指定类型的文件",
#                 "example": "财务报表 filetype:pdf"
#             },
#             {
#                 "pattern": "组合使用",
#                 "description": "多种语法组合",
#                 "example": "\"财务报告\" -草稿 filetype:docx"
#             }
#         ],
#         "search_types": [
#             {
#                 "type": "keyword",
#                 "name": "关键词检索",
#                 "description": "BM25算法，适合精确匹配"
#             },
#             {
#                 "type": "vector",
#                 "name": "向量检索",
#                 "description": "语义相似度匹配"
#             },
#             {
#                 "type": "hybrid",
#                 "name": "混合检索",
#                 "description": "结合向量和关键词（推荐）"
#             },
#             {
#                 "type": "smart",
#                 "name": "智能检索",
#                 "description": "LLM增强，需要配置API"
#             }
#         ]
#     })
