from fastapi import APIRouter
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from utils.storage import (
    get_document_info,
    save_classification_result,
    get_documents_by_classification,
    get_all_documents
)
from utils.classifier import classify_document, create_classification_directory
from utils.multi_level_classifier import (
    get_multi_level_classifier,
    build_and_save_classification_tree,
    get_classification_tree
)
from api import success, fail, BusinessException

logger = logging.getLogger(__name__)

router = APIRouter()

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

@router.post("/classify", summary="对单个文档进行智能分类")
async def classify_single_document(request: ClassificationRequest):
    doc_info = get_document_info(request.document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {request.document_id}")
    
    classification_result = classify_document(doc_info)
    if not classification_result:
        raise BusinessException(code=1005, detail="文档分类处理失败")
    
    result_data = classification_result.get('classification_result', {})
    categories = result_data.get('categories', [])
    
    if categories:
        save_classification_result(
            request.document_id,
            categories[0]
        )
    
    logger.info(f"文档分类完成: {request.document_id} -> {categories}")
    
    return success(data={
        "document_id": request.document_id,
        "filename": doc_info.get('filename', ''),
        "categories": categories,
        "confidence": result_data.get('confidence', 0.0),
        "suggested_folders": result_data.get('suggested_folders', [])
    }, message="文档分类完成")

@router.get("/categories", summary="获取所有分类列表")
async def get_all_categories():
    all_docs = get_all_documents()
    category_count = {}
    
    for doc in all_docs:
        category = doc.get('classification_result', '未分类')
        category_count[category] = category_count.get(category, 0) + 1
    
    return success(data={
        "categories": list(category_count.keys()),
        "document_count": category_count
    })

@router.get("/documents/{category}", summary="获取指定分类下的文档")
async def get_documents_by_category(category: str):
    docs = get_documents_by_classification(category)
    
    items = [{
        "id": doc.get("id"),
        "filename": doc.get("filename"),
        "file_type": doc.get("file_type"),
        "classification_result": doc.get("classification_result")
    } for doc in docs]
    
    return success(data={
        "category": category,
        "total": len(items),
        "documents": items
    })

@router.post("/create-folder/{document_id}", summary="自动创建分类目录并移动文件")
async def create_document_folder(document_id: str):
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    if not doc_info.get('classification_result'):
        raise BusinessException(code=1006, detail="文档尚未分类，请先执行分类")
    
    success_flag, target_path = create_classification_directory(
        doc_info,
        [doc_info['classification_result']]
    )
    
    if not success_flag:
        raise BusinessException(code=1005, detail="分类目录创建失败")
    
    logger.info(f"分类目录创建成功: {document_id} -> {target_path}")
    
    return success(data={
        "document_id": document_id,
        "target_path": target_path
    }, message="分类目录创建成功，文件已移动")

@router.post("/multi-level/build", summary="构建多级分类树")
async def build_multi_level_classification(request: MultiLevelClassificationRequest):
    """
    构建多级分类树（内容 → 类型 → 时间）
    """
    try:
        logger.info("开始构建多级分类树...")
        
        if request.force_rebuild:
            tree = build_and_save_classification_tree()
        else:
            tree = get_classification_tree()
        
        logger.info(f"多级分类树构建完成，共 {tree.get('total_documents', 0)} 个文档")
        
        return success(data=tree, message="多级分类树构建成功")
    except Exception as e:
        logger.error(f"构建多级分类树失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"构建多级分类树失败: {str(e)}")

@router.get("/multi-level/tree", summary="获取多级分类树")
async def get_multi_level_tree():
    """
    获取已构建的多级分类树
    """
    try:
        tree = get_classification_tree()
        if not tree:
            return success(data={
                "generated_at": "",
                "total_documents": 0,
                "tree": {}
            }, message="分类树为空，请先构建")
        
        return success(data=tree, message="获取分类树成功")
    except Exception as e:
        logger.error(f"获取多级分类树失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"获取多级分类树失败: {str(e)}")

@router.get("/multi-level/document/{document_id}", summary="获取单个文档的多级分类信息")
async def get_document_multi_level_classification(document_id: str):
    """
    获取单个文档的多级分类详细信息
    """
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
        
        classifier = get_multi_level_classifier()
        classification = classifier.classify_document(doc_info)
        
        if not classification:
            raise BusinessException(code=1005, detail="文档分类失败")
        
        return success(data=classification, message="获取文档多级分类信息成功")
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"获取文档多级分类信息失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"获取文档多级分类信息失败: {str(e)}")
