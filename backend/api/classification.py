from fastapi import APIRouter
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from utils.storage import (
    get_document_info,
    save_classification_result,
    get_documents_by_classification,
    get_all_documents,
    update_document_info,
    update_classification_tree_after_reclassify,
    re_chunk_document
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

@router.post("/reclassify/{document_id}", summary="重新分类文档")
async def reclassify_document(document_id: str):
    """
    对已分类的文档进行重新分类
    会清除旧的分类结果并重新进行智能分类
    """
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    old_classification = doc_info.get('classification_result')
    
    classification_result = classify_document(doc_info)
    if not classification_result:
        raise BusinessException(code=1005, detail="文档分类处理失败")
    
    result_data = classification_result.get('classification_result', {})
    categories = result_data.get('categories', [])
    
    if categories:
        save_classification_result(
            document_id,
            categories[0]
        )
        update_classification_tree_after_reclassify(
            document_id,
            old_classification,
            categories[0]
        )
    
    logger.info(f"文档重新分类完成: {document_id} -> {categories}")
    
    return success(data={
        "document_id": document_id,
        "filename": doc_info.get('filename', ''),
        "old_classification": old_classification,
        "new_classification": categories[0] if categories else None,
        "categories": categories,
        "confidence": result_data.get('confidence', 0.0)
    }, message="文档重新分类完成")

@router.delete("/result/{document_id}", summary="清除文档分类结果")
async def clear_classification_result(document_id: str):
    """
    清除文档的分类结果，使其变为未分类状态
    同时更新分类树
    """
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    old_classification = doc_info.get('classification_result')
    if not old_classification:
        return success(data={
            "document_id": document_id,
            "message": "文档本身未分类，无需清除"
        }, message="文档未分类")
    
    update_document_info(document_id, {
        'classification_result': None,
        'classification_time': None
    })
    
    update_classification_tree_after_reclassify(
        document_id,
        old_classification,
        None
    )
    
    logger.info(f"文档分类结果已清除: {document_id}")
    
    return success(data={
        "document_id": document_id,
        "old_classification": old_classification
    }, message="分类结果已清除")

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
    
    # 更新文档信息中的 filepath 为新路径
    if target_path:
        update_document_info(document_id, {'filepath': target_path})
    
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


class CategoryBatchRequest(BaseModel):
    category: str
    use_refiner: bool = True


@router.post("/category/batch-rechunk", summary="分类下所有文档批量重新分片")
async def category_batch_rechunk(request: CategoryBatchRequest):
    """对指定分类下的所有文档进行批量重新分片"""
    docs = get_documents_by_classification(request.category)
    if not docs:
        return success(data={
            "total": 0,
            "success_count": 0,
            "results": []
        }, message="该分类下没有文档")
    
    results = []
    for doc in docs:
        try:
            is_success = re_chunk_document(doc['id'], use_refiner=request.use_refiner)
            results.append({
                "document_id": doc['id'],
                "filename": doc.get('filename', ''),
                "success": is_success
            })
        except Exception as e:
            logger.error(f"分类下文档重新分片失败 {doc['id']}: {str(e)}")
            results.append({
                "document_id": doc['id'],
                "filename": doc.get('filename', ''),
                "success": False,
                "error": str(e)
            })
    
    success_count = sum(1 for r in results if r['success'])
    return success(data={
        "category": request.category,
        "total": len(results),
        "success_count": success_count,
        "results": results
    }, message=f"分类下批量重新分片完成，成功 {success_count}/{len(results)}")


@router.post("/category/batch-reclassify", summary="分类下所有文档批量重新分类")
async def category_batch_reclassify(request: CategoryBatchRequest):
    """对指定分类下的所有文档进行批量重新分类"""
    docs = get_documents_by_classification(request.category)
    if not docs:
        return success(data={
            "total": 0,
            "success_count": 0,
            "results": []
        }, message="该分类下没有文档")
    
    results = []
    for doc in docs:
        try:
            doc_info = get_document_info(doc['id'])
            if not doc_info:
                results.append({
                    "document_id": doc['id'],
                    "filename": doc.get('filename', ''),
                    "success": False,
                    "error": "文档不存在"
                })
                continue
            
            old_classification = doc_info.get('classification_result')
            classification_result = classify_document(doc_info)
            if not classification_result:
                results.append({
                    "document_id": doc['id'],
                    "filename": doc.get('filename', ''),
                    "success": False,
                    "error": "分类失败"
                })
                continue
            
            result_data = classification_result.get('classification_result', {})
            categories = result_data.get('categories', [])
            new_classification = categories[0] if categories else None
            
            if new_classification:
                save_classification_result(doc['id'], new_classification)
                update_classification_tree_after_reclassify(
                    doc['id'],
                    old_classification,
                    new_classification
                )
            
            results.append({
                "document_id": doc['id'],
                "filename": doc.get('filename', ''),
                "success": True,
                "old_classification": old_classification,
                "new_classification": new_classification
            })
        except Exception as e:
            logger.error(f"分类下文档重新分类失败 {doc['id']}: {str(e)}")
            results.append({
                "document_id": doc['id'],
                "filename": doc.get('filename', ''),
                "success": False,
                "error": str(e)
            })
    
    success_count = sum(1 for r in results if r['success'])
    return success(data={
        "category": request.category,
        "total": len(results),
        "success_count": success_count,
        "results": results
    }, message=f"分类下批量重新分类完成，成功 {success_count}/{len(results)}")
