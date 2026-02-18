from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import List
import os
import shutil
from pathlib import Path
from utils.storage import (
    save_document_summary_for_classification,
    save_document_to_chroma,
    get_document_info,
    get_all_documents,
    delete_document,
    DOC_DIR
)
from pydantic import BaseModel

# 定义响应模型，前端对接有明确的格式规范
class DocumentInfo(BaseModel):
    id: str
    filename: str
    file_type: str
    preview_content: str
    full_content_length: int
    created_at_iso: str
    classification_result: str | None = None

class DeleteResponse(BaseModel):
    status: str
    message: str
    document_id: str

# 初始化路由
router = APIRouter()

# 允许的文件类型，和document_processor里的处理器对应
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.ppt', '.pptx', '.eml', '.msg', '.txt'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB，和document_processor一致

@router.post("/upload", summary="上传文档", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)):
    """
    上传办公文档，自动保存文档信息、解析内容、存入向量库
    """
    # 1. 校验文件类型
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型，仅支持：{', '.join(ALLOWED_EXTENSIONS)}")

    # 2. 校验文件大小
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，最大支持50MB")
    
    # 3. 保存文件到本地
    file_path = DOC_DIR / filename
    # 处理重名文件
    counter = 1
    while file_path.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        file_path = DOC_DIR / f"{stem}_{counter}{suffix}"
        counter += 1
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # 4. 保存文档摘要（用于分类）
    document_id, doc_info = save_document_summary_for_classification(str(file_path))
    if not document_id:
        # 失败时删除本地文件
        os.remove(file_path)
        raise HTTPException(status_code=500, detail="文档解析失败，请检查文件是否损坏")
    
    # 5. 存入Chroma向量库
    save_success = save_document_to_chroma(str(file_path), document_id=document_id)
    if not save_success:
        # 失败时清理数据
        delete_document(document_id)
        os.remove(file_path)
        raise HTTPException(status_code=500, detail="文档存入向量库失败")
    
    return doc_info

@router.get("/", summary="获取所有文档列表", response_model=List[DocumentInfo])
async def get_document_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量")
):
    """
    分页获取所有文档的信息
    """
    all_docs = get_all_documents()
    # 分页处理
    start = (page - 1) * page_size
    end = start + page_size
    return all_docs[start:end]

@router.get("/{document_id}", summary="获取文档详情", response_model=DocumentInfo)
async def get_document_detail(document_id: str):
    """
    根据文档ID获取文档的详细信息
    """
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc_info

@router.delete("/{document_id}", summary="删除文档", response_model=DeleteResponse)
async def delete_document_api(document_id: str):
    """
    根据文档ID删除文档，同时删除本地文件、元数据和向量库数据
    """
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 删除本地文件
    file_path = Path(doc_info['filepath'])
    if file_path.exists():
        os.remove(file_path)
    
    # 删除元数据和向量库数据
    delete_success = delete_document(document_id)
    if not delete_success:
        raise HTTPException(status_code=500, detail="文档删除失败")
    
    return {
        "status": "success",
        "message": "文档删除成功",
        "document_id": document_id
    }