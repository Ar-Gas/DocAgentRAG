from fastapi import APIRouter, HTTPException
from typing import List, Dict
from pydantic import BaseModel
from utils.storage import (
    get_document_info,
    save_classification_result,
    get_documents_by_classification,
    get_all_documents
)
from utils.classifier import classify_document, create_classification_directory

router = APIRouter()

# 响应模型
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

@router.post("/classify", summary="对单个文档进行智能分类", response_model=ClassificationResponse)
async def classify_single_document(request: ClassificationRequest):
    """
    对指定文档进行智能分类，并保存分类结果
    """
    # 校验文档是否存在
    doc_info = get_document_info(request.document_id)
    if not doc_info:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 执行分类
    classification_result = classify_document(doc_info)
    if not classification_result:
        raise HTTPException(status_code=500, detail="文档分类失败")
    
    # 保存分类结果到元数据
    save_classification_result(
        request.document_id,
        classification_result['classification_result']['categories'][0]
    )
    
    return classification_result['classification_result']

@router.get("/categories", summary="获取所有分类列表", response_model=CategoryListResponse)
async def get_all_categories():
    """
    获取所有分类标签，以及每个分类下的文档数量
    """
    all_docs = get_all_documents()
    category_count = {}
    
    for doc in all_docs:
        category = doc.get('classification_result', '未分类')
        category_count[category] = category_count.get(category, 0) + 1
    
    return {
        "categories": list(category_count.keys()),
        "document_count": category_count
    }

@router.get("/documents/{category}", summary="获取指定分类下的文档")
async def get_documents_by_category(category: str):
    """
    根据分类标签，获取该分类下的所有文档
    """
    docs = get_documents_by_classification(category)
    return docs

@router.post("/create-folder/{document_id}", summary="自动创建分类目录并移动文件")
async def create_document_folder(document_id: str):
    """
    根据文档的分类结果，自动创建分类目录，并移动文件到对应目录
    """
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    if not doc_info.get('classification_result'):
        raise HTTPException(status_code=400, detail="文档尚未分类，请先执行分类")
    
    # 执行目录创建和文件移动
    success, target_path = create_classification_directory(
        doc_info,
        [doc_info['classification_result']]
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="分类目录创建失败")
    
    return {
        "status": "success",
        "message": "分类目录创建成功，文件已移动",
        "target_path": target_path
    }