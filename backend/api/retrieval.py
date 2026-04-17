from fastapi import APIRouter, Query, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, validator
import asyncio
import json
import tempfile
import os

# 0.3 合法文件类型 allowlist
ALLOWED_FILE_TYPES = {"pdf", "word", "excel", "ppt", "eml", "txt", "image"}

from app.core.logger import logger
from app.services.errors import AppServiceError
from app.services.retrieval_service import RetrievalService
from utils.retriever import (
    multimodal_search,
)
from utils.smart_retrieval import (
    smart_multimodal_retrieval,
    llm_rerank,
    is_llm_available,
)
from api import success, BusinessException

router = APIRouter()
retrieval_service = RetrievalService()

class BatchSearchRequest(BaseModel):
    queries: List[str]
    limit: int = 5

def _validate_file_types(v):
    """校验 file_types 列表只包含合法值"""
    if v:
        invalid = set(v) - ALLOWED_FILE_TYPES
        if invalid:
            raise ValueError(f"不支持的文件类型: {invalid}，合法值: {ALLOWED_FILE_TYPES}")
    return v


class HybridSearchRequest(BaseModel):
    query: str
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = True
    file_types: Optional[List[str]] = None

    @validator("file_types")
    def validate_file_types(cls, v):
        return _validate_file_types(v)


class SmartSearchRequest(BaseModel):
    query: str
    limit: int = 10
    use_query_expansion: bool = True
    use_llm_rerank: bool = True
    expansion_method: str = 'llm'
    file_types: Optional[List[str]] = None

    @validator("file_types")
    def validate_file_types(cls, v):
        return _validate_file_types(v)


class WorkspaceSearchRequest(BaseModel):
    query: str = ""
    mode: str = "hybrid"
    retrieval_version: Optional[str] = None
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = False
    use_query_expansion: bool = True
    use_llm_rerank: bool = True
    expansion_method: str = "llm"
    file_types: Optional[List[str]] = None
    filename: Optional[str] = None
    classification: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    group_by_document: bool = True

    @validator("file_types")
    def validate_file_types(cls, v):
        return _validate_file_types(v)

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
    file_type_list = [ft.strip().lstrip('.') for ft in file_types.split(',') if ft.strip()] if file_types else None
    if file_type_list:
        invalid = set(file_type_list) - ALLOWED_FILE_TYPES
        if invalid:
            raise BusinessException(code=400, detail=f"不支持的文件类型: {invalid}")
    try:
        result = retrieval_service.search(query, limit, use_rerank, file_type_list)
        logger.info(f"语义检索完成: query='{query[:50]}...', results={result['total']}, rerank={use_rerank}, filters={file_type_list}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.post("/hybrid-search", summary="混合检索（向量+BM25关键词）")
async def hybrid_search_api(request: HybridSearchRequest):
    try:
        alpha = max(0.0, min(1.0, request.alpha))
        result = retrieval_service.hybrid(request.query, request.limit, alpha, request.use_rerank, request.file_types)
        logger.info(f"混合检索完成: query='{request.query[:50]}...', alpha={alpha}, results={result['total']}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.post("/batch-search", summary="批量查询语义检索")
async def batch_search_document_api(request: BatchSearchRequest):
    try:
        result = retrieval_service.batch(request.queries, request.limit)
        logger.info(f"批量检索完成: queries={len(request.queries)}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/document/{document_id}", summary="根据ID获取文档全部分片")
async def get_document_chunks(document_id: str):
    try:
        return success(data=retrieval_service.get_document_chunks(document_id))
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/stats", summary="获取文档库统计信息")
async def get_document_stats_api():
    return success(data=retrieval_service.stats())

@router.post("/smart-search", summary="智能检索（查询扩展+多查询+LLM重排序）")
async def smart_search_api(request: SmartSearchRequest):
    try:
        result = retrieval_service.smart(
            request.query,
            request.limit,
            request.use_query_expansion,
            request.use_llm_rerank,
            request.expansion_method,
            request.file_types,
        )
        logger.info(
            "智能检索完成: query='%s...', expansions=%s, results=%s",
            request.query[:50],
            len(result["meta"]["expanded_queries"]),
            result["total"],
        )
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.post("/workspace-search", summary="工作台统一检索")
async def workspace_search_api(request: WorkspaceSearchRequest):
    try:
        result = retrieval_service.workspace_search(
            query=request.query,
            mode=request.mode,
            retrieval_version=request.retrieval_version,
            limit=request.limit,
            alpha=request.alpha,
            use_rerank=request.use_rerank,
            use_query_expansion=request.use_query_expansion,
            use_llm_rerank=request.use_llm_rerank,
            expansion_method=request.expansion_method,
            file_types=request.file_types,
            filename=request.filename,
            classification=request.classification,
            date_from=request.date_from,
            date_to=request.date_to,
            group_by_document=request.group_by_document,
        )
        logger.info(
            "工作台检索完成: query='%s...', mode=%s, results=%s, documents=%s",
            (request.query or "")[:50],
            request.mode,
            result["total_results"],
            result["total_documents"],
        )
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/expand-query", summary="查询扩展预览")
async def expand_query_api(
    query: str = Query(..., description="原始查询"),
    method: str = Query('llm', description="扩展方法: llm 或 keyword")
):
    try:
        return success(data=retrieval_service.expand_query(query, method))
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/llm-status", summary="检查LLM服务状态")
async def check_llm_status():
    return success(data=retrieval_service.llm_status())


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
    try:
        result = retrieval_service.multimodal(request.query, request.image_url, request.limit, request.file_types)
        logger.info(f"多模态检索完成: query='{request.query[:50] if request.query else ''}', has_image={bool(request.image_url)}, results={result['total']}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


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
    try:
        result = retrieval_service.keyword(request.query, request.limit, request.file_types)
        logger.info(f"关键词检索完成: query='{request.query[:50]}...', results={result['total']}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


class SearchWithHighlightRequest(BaseModel):
    query: str
    search_type: str = "hybrid"
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = False
    file_types: Optional[List[str]] = None


class SummarizeResultsRequest(BaseModel):
    query: str
    results: List[Dict[str, Any]] = []


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
    valid_types = ['keyword', 'vector', 'hybrid', 'smart']
    search_type = request.search_type if request.search_type in valid_types else 'hybrid'
    try:
        result = retrieval_service.search_highlight(
            request.query,
            search_type,
            request.limit,
            request.alpha,
            request.use_rerank,
            request.file_types,
        )
        logger.info(f"带高亮检索完成: query='{request.query[:50]}...', type={search_type}, results={result['total']}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.post("/summarize-results", summary="对检索结果生成总结")
async def summarize_results_api(request: SummarizeResultsRequest):
    try:
        result = retrieval_service.summarize_results(request.query, request.results)
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


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
    
    results = multimodal_search(
        query=request.query,
        image_url=request.image_url,
        limit=request.limit,
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
            return multimodal_search(
                query=q,
                image_url=image_url,
                image_path=image_path,
                limit=limit,
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


# ===================== 3.3 Smart Search SSE =====================

@router.post("/workspace-search-stream", summary="智能检索 SSE 流（先返回 hybrid，后推 LLM rerank）")
async def workspace_search_stream(req: WorkspaceSearchRequest):
    """
    两阶段流式响应：
    - event: results  → 立即返回 block 工作台检索结果（hybrid 排序模式）
    - event: reranked → LLM rerank 完成后推送（仅 smart 模式且 LLM 可用时）
    - event: done     → 流结束

    前端可立即渲染 results，reranked 到来后更新排序。
    """
    async def event_generator():
        loop = asyncio.get_event_loop()

        # Phase 1：hybrid 检索，立即返回
        try:
            hybrid_result = await loop.run_in_executor(
                None,
                lambda: retrieval_service.workspace_search(
                    query=req.query,
                    mode="hybrid",
                    retrieval_version=req.retrieval_version,
                    limit=req.limit,
                    alpha=req.alpha,
                    use_rerank=req.use_rerank,
                    file_types=req.file_types,
                    filename=req.filename,
                    classification=req.classification,
                    date_from=req.date_from,
                    date_to=req.date_to,
                    group_by_document=req.group_by_document,
                ),
            )
            yield f"event: results\ndata: {json.dumps(hybrid_result, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error(f"SSE hybrid search 失败: {exc}")
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        # Phase 2：LLM rerank（仅 smart 模式 + LLM 可用）
        if req.mode == "smart" and req.use_llm_rerank and is_llm_available():
            try:
                raw_results = hybrid_result.get("results", [])
                if raw_results:
                    reranked_results = await loop.run_in_executor(
                        None,
                        lambda: llm_rerank(req.query, raw_results, req.limit),
                    )
                    reranked_payload = {**hybrid_result, "results": reranked_results, "mode": "smart"}
                    regroup = getattr(retrieval_service, "regroup_workspace_payload", None)
                    if callable(regroup):
                        try:
                            reranked_payload = regroup(reranked_payload, reranked_results, req.query)
                        except Exception as regroup_exc:
                            logger.warning(f"SSE reranked regroup 失败，保留原 rerank results: {regroup_exc}")
                    yield f"event: reranked\ndata: {json.dumps(reranked_payload, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.warning(f"SSE LLM rerank 失败（降级保留 hybrid 结果）: {exc}")
                yield f"event: rerank_error\ndata: {json.dumps({'error': str(exc)})}\n\n"

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
