from fastapi import APIRouter, UploadFile, File, Query
from typing import List
import os
from pathlib import Path
import logging

from utils.storage import (
    save_document_summary_for_classification,
    save_document_to_chroma,
    get_document_info,
    get_all_documents,
    delete_document,
    DOC_DIR
)
from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, EXTENSION_TO_DIR
from api import success, fail, paginated, BusinessException

logger = logging.getLogger(__name__)

router = APIRouter()

class DocumentInfo:
    id: str
    filename: str
    file_type: str
    preview_content: str
    full_content_length: int
    created_at_iso: str
    classification_result: str | None = None

def _build_document_response(doc_info: dict) -> dict:
    return {
        "id": doc_info.get("id"),
        "filename": doc_info.get("filename"),
        "file_type": doc_info.get("file_type"),
        "preview_content": doc_info.get("preview_content", "")[:500],
        "full_content_length": doc_info.get("full_content_length", 0),
        "created_at_iso": doc_info.get("created_at_iso"),
        "classification_result": doc_info.get("classification_result")
    }

@router.post("/upload", summary="上传文档")
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        raise BusinessException(
            code=2001, 
            detail=f"不支持的文件类型，仅支持：{', '.join(ALLOWED_EXTENSIONS)}"
        )

    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise BusinessException(
            code=2002, 
            detail=f"文件过大，最大支持{MAX_FILE_SIZE // 1024 // 1024}MB"
        )
    
    type_subdir = EXTENSION_TO_DIR.get(ext, 'other')
    target_dir = DOC_DIR / type_subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / filename
    counter = 1
    while file_path.exists():
        stem = file_path.stem
        suffix = file_path.suffix
        file_path = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    document_id, doc_info = save_document_summary_for_classification(str(file_path))
    if not document_id:
        os.remove(file_path)
        raise BusinessException(code=1002, detail="文档解析失败，请检查文件是否损坏")
    
    save_success = save_document_to_chroma(str(file_path), document_id=document_id)
    if not save_success:
        delete_document(document_id)
        os.remove(file_path)
        raise BusinessException(code=1003, detail="文档存入向量库失败")
    
    logger.info(f"文档上传成功: {filename}, id={document_id}, 存储路径: {file_path}")
    return success(data=_build_document_response(doc_info), message="文档上传成功")

@router.get("/", summary="获取所有文档列表")
async def get_document_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量")
):
    all_docs = get_all_documents()
    total = len(all_docs)
    
    start = (page - 1) * page_size
    end = start + page_size
    
    items = [_build_document_response(doc) for doc in all_docs[start:end]]
    
    return paginated(items=items, total=total, page=page, page_size=page_size)

@router.get("/{document_id}", summary="获取文档详情")
async def get_document_detail(document_id: str):
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    return success(data=_build_document_response(doc_info))

@router.delete("/{document_id}", summary="删除文档")
async def delete_document_api(document_id: str):
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    file_path = Path(doc_info.get('filepath', ''))
    if file_path.exists():
        os.remove(file_path)
    
    delete_success = delete_document(document_id)
    if not delete_success:
        raise BusinessException(code=1004, detail=f"文档ID: {document_id}")
    
    logger.info(f"文档删除成功: {document_id}")
    return success(
        data={"document_id": document_id}, 
        message="文档删除成功"
    )
