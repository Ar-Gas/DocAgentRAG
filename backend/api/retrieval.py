from fastapi import APIRouter, Depends, Query, File, UploadFile, Form
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict, validator
import logging
import tempfile
import os

# 0.3 合法文件类型 allowlist
ALLOWED_FILE_TYPES = {"pdf", "word", "excel", "ppt", "eml", "txt", "image"}

from app.services.errors import AppServiceError
from app.services.retrieval_service import RetrievalService
from utils.retriever import (
    multimodal_search,
    hybrid_multimodal_search,
)
from api import success, BusinessException
from api.dependencies import require_authenticated_user

logger = logging.getLogger(__name__)

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


class WorkspaceSearchRequest(BaseModel):
    query: str = ""
    mode: str = "hybrid"
    limit: int = 10
    alpha: float = 0.5
    use_rerank: bool = False
    file_types: Optional[List[str]] = None
    filename: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    group_by_document: bool = True
    visibility_scope: Optional[str] = None
    department_id: Optional[str] = None
    business_category_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

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

@router.get("/search", summary="单查询检索")
async def search_document_api(
    query: str = Query(..., description="检索关键词/句子"),
    limit: int = Query(10, ge=1, le=100, description="返回结果数量"),
    use_rerank: bool = Query(False, description="是否使用重排序提升结果质量"),
    file_types: str = Query(None, description="文件类型过滤，逗号分隔，如 'pdf,docx'"),
    current_user: dict = Depends(require_authenticated_user),
):
    file_type_list = [ft.strip().lstrip('.') for ft in file_types.split(',') if ft.strip()] if file_types else None
    if file_type_list:
        invalid = set(file_type_list) - ALLOWED_FILE_TYPES
        if invalid:
            raise BusinessException(code=400, detail=f"不支持的文件类型: {invalid}")
    try:
        result = retrieval_service.search(query, limit, use_rerank, file_type_list, current_user=current_user)
        logger.info(
            "检索完成: query='%s...', results=%s, rerank=%s, filters=%s",
            query[:50],
            result["total"],
            use_rerank,
            file_type_list,
        )
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.post("/hybrid-search", summary="混合检索（向量+BM25关键词）")
async def hybrid_search_api(
    request: HybridSearchRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        alpha = max(0.0, min(1.0, request.alpha))
        result = retrieval_service.hybrid(
            request.query,
            request.limit,
            alpha,
            request.use_rerank,
            request.file_types,
            current_user=current_user,
        )
        logger.info(f"混合检索完成: query='{request.query[:50]}...', alpha={alpha}, results={result['total']}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.post("/batch-search", summary="批量查询检索")
async def batch_search_document_api(
    request: BatchSearchRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        result = retrieval_service.batch(request.queries, request.limit, current_user=current_user)
        logger.info(f"批量检索完成: queries={len(request.queries)}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/document/{document_id}", summary="根据ID获取文档全部分片")
async def get_document_chunks(
    document_id: str,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        return success(data=retrieval_service.get_document_chunks(document_id, current_user=current_user))
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/stats", summary="获取文档库统计信息")
async def get_document_stats_api(current_user: dict = Depends(require_authenticated_user)):
    return success(data=retrieval_service.stats(current_user=current_user))

@router.post("/workspace-search", summary="工作台统一检索")
async def workspace_search_api(
    request: WorkspaceSearchRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        result = retrieval_service.workspace_search(
            query=request.query,
            mode=request.mode,
            limit=request.limit,
            alpha=request.alpha,
            use_rerank=request.use_rerank,
            file_types=request.file_types,
            filename=request.filename,
            date_from=request.date_from,
            date_to=request.date_to,
            group_by_document=request.group_by_document,
            visibility_scope=request.visibility_scope,
            department_id=request.department_id,
            business_category_id=request.business_category_id,
            current_user=current_user,
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
async def multimodal_search_api(
    request: MultimodalSearchRequest,
    current_user: dict = Depends(require_authenticated_user),
):
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
        result = retrieval_service.multimodal(
            request.query,
            request.image_url,
            request.limit,
            request.file_types,
            current_user=current_user,
        )
        logger.info(f"多模态检索完成: query='{request.query[:50] if request.query else ''}', has_image={bool(request.image_url)}, results={result['total']}")
        return success(data=result)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.post("/multimodal-search-upload", summary="多模态检索（上传图片）")
async def multimodal_search_upload_api(
    query: str = Form(default=""),
    image: UploadFile = File(default=None),
    limit: int = Form(default=10),
    file_types: str = Form(default=None),
    current_user: dict = Depends(require_authenticated_user),
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
        results = retrieval_service.collect_visible_results(
            lambda fetch_limit: multimodal_search(
                query=query,
                image_path=image_path,
                limit=fetch_limit,
                file_types=file_type_list,
            ),
            limit,
            current_user,
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
async def keyword_search_api(
    request: KeywordSearchRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        result = retrieval_service.keyword(
            request.query,
            request.limit,
            request.file_types,
            current_user=current_user,
        )
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


@router.post("/search-with-highlight", summary="带关键词高亮的检索")
async def search_with_highlight_api(
    request: SearchWithHighlightRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    """
    带关键词高亮的检索功能
    
    特点：
    - 自动提取查询中的关键词
    - 在检索结果中高亮匹配的关键词
    - 返回匹配的关键词列表
    
    search_type 选项：
    - keyword: 精确关键词检索
    - vector: 向量检索
    - hybrid: 混合检索（向量+关键词）
    """
    valid_types = ['keyword', 'vector', 'hybrid']
    search_type = request.search_type if request.search_type in valid_types else 'hybrid'
    try:
        result = retrieval_service.search_highlight(
            request.query,
            search_type,
            request.limit,
            request.alpha,
            request.use_rerank,
            request.file_types,
            current_user=current_user,
        )
        logger.info(f"带高亮检索完成: query='{request.query[:50]}...', type={search_type}, results={result['total']}")
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
                "name": "向量检索",
                "description": "使用向量相似度匹配内容接近的资料，适合制度问答和背景检索",
                "supports_highlight": True
            },
            {
                "type": "hybrid",
                "name": "混合检索",
                "description": "结合向量检索和关键词检索，可调节权重",
                "supports_highlight": True,
                "has_alpha": True
            }
        ]
    })


@router.post("/hybrid-multimodal-search", summary="混合多模态检索")
async def hybrid_multimodal_search_api(
    request: HybridMultimodalSearchRequest,
    current_user: dict = Depends(require_authenticated_user),
):
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
    
    results = retrieval_service.collect_visible_results(
        lambda fetch_limit: hybrid_multimodal_search(
            query=request.query,
            image_url=request.image_url,
            limit=fetch_limit,
            alpha=alpha,
            use_rerank=request.use_rerank,
            file_types=request.file_types,
        ),
        request.limit,
        current_user,
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

