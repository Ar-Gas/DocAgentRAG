from fastapi import APIRouter, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from app.services.classification_service import ClassificationService
from app.services.errors import AppServiceError
from api import success, BusinessException
from api.dependencies import require_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter()
classification_service = ClassificationService()

class ClassificationRequest(BaseModel):
    document_id: str

class ClassificationResponse(BaseModel):
    document_id: str
    filename: str
    categories: List[str]
    confidence: float
    suggested_folders: List[str]

class CategoryListResponse(BaseModel):
    categories: List[str]
    document_count: Dict[str, int]

class MultiLevelClassificationRequest(BaseModel):
    force_rebuild: bool = False


class TopicTreeBuildRequest(BaseModel):
    force_rebuild: bool = False


class ClassificationTableGenerateRequest(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    persist: bool = True


class ClassificationTableListRequest(BaseModel):
    limit: int = 50

@router.post("/classify", summary="对单个文档进行智能分类")
async def classify_single_document(request: ClassificationRequest):
    try:
        result = classification_service.classify(request.document_id)
        logger.info(f"文档分类完成: {request.document_id} -> {result.get('categories', [])}")
        return success(data=result, message="文档分类完成")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.post("/reclassify/{document_id}", summary="重新分类文档")
async def reclassify_document(document_id: str):
    try:
        result = classification_service.reclassify(document_id)
        logger.info(f"文档重新分类完成: {document_id} -> {result.get('categories', [])}")
        return success(data=result, message="文档重新分类完成")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.delete("/result/{document_id}", summary="清除文档分类结果")
async def clear_classification_result(document_id: str):
    try:
        result = classification_service.clear(document_id)
        logger.info(f"文档分类结果已清除: {document_id}")
        return success(data=result, message="分类结果已清除" if result.get("old_classification") else "文档未分类")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/categories", summary="获取所有分类列表")
async def get_all_categories():
    return success(data=classification_service.get_categories())

@router.get("/documents/{category}", summary="获取指定分类下的文档")
async def get_documents_by_category(category: str):
    return success(data=classification_service.get_documents_by_category(category))

@router.post("/multi-level/build", summary="构建多级分类树")
async def build_multi_level_classification(request: MultiLevelClassificationRequest):
    try:
        tree = classification_service.build_multi_level_tree(request.force_rebuild)
        return success(data=tree, message="多级分类树构建成功")
    except Exception as e:
        logger.error(f"构建多级分类树失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"构建多级分类树失败: {str(e)}")


@router.post("/topic-tree/build", summary="重建动态语义主题树")
async def build_topic_tree(
    request: TopicTreeBuildRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        classification_service.build_topic_tree(request.force_rebuild)
        tree = classification_service.get_topic_tree(current_user=current_user)
        return success(data=tree, message="动态主题树构建成功")
    except Exception as e:
        logger.error(f"构建动态主题树失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"构建动态主题树失败: {str(e)}")


@router.get("/topic-tree", summary="获取动态语义主题树")
async def get_topic_tree(current_user: dict = Depends(require_authenticated_user)):
    try:
        tree = classification_service.get_topic_tree(current_user=current_user)
        return success(data=tree, message="获取动态主题树成功")
    except Exception as e:
        logger.error(f"获取动态主题树失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"获取动态主题树失败: {str(e)}")


@router.get("/multi-level/tree", summary="获取多级分类树")
async def get_multi_level_tree():
    try:
        tree = classification_service.get_multi_level_tree()
        return success(data=tree, message="获取分类树成功")
    except Exception as e:
        logger.error(f"获取多级分类树失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"获取多级分类树失败: {str(e)}")

@router.get("/multi-level/document/{document_id}", summary="获取单个文档的多级分类信息")
async def get_document_multi_level_classification(document_id: str):
    try:
        classification = classification_service.get_document_multi_level_info(document_id)
        return success(data=classification, message="获取文档多级分类信息成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)
    except Exception as e:
        logger.error(f"获取文档多级分类信息失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"获取文档多级分类信息失败: {str(e)}")


@router.post("/tables/generate", summary="根据检索结果生成分类表")
async def generate_classification_table(request: ClassificationTableGenerateRequest):
    try:
        result = classification_service.generate_classification_table(
            request.query,
            request.results,
            persist=request.persist,
        )
        return success(data=result, message="分类表生成成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/tables", summary="获取历史分类表")
async def list_classification_tables(limit: int = 50):
    return success(data=classification_service.list_classification_tables(limit))


@router.get("/tables/{table_id}", summary="获取单个分类表")
async def get_classification_table(table_id: str):
    try:
        return success(data=classification_service.get_classification_table(table_id))
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)
