from fastapi import APIRouter, UploadFile, File, Query
from typing import List
from pydantic import BaseModel
import os
from pathlib import Path
import logging

from utils.storage import (
    save_document_summary_for_classification,
    save_document_to_chroma,
    get_document_info,
    get_all_documents,
    delete_document,
    re_chunk_document,
    check_document_chunks,
    DOC_DIR
)
from utils.content_refiner import ContentRefiner
from utils.document_processor import process_document
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
        raise BusinessException(code=1002, detail="文档解析失败，请检查文件是否损坏或格式是否正确")
    
    save_success = save_document_to_chroma(str(file_path), document_id=document_id)
    if not save_success:
        delete_document(document_id)
        os.remove(file_path)
        raise BusinessException(code=1003, detail="文档存入向量库失败，请检查后端日志了解详细原因")
    
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
    file_deleted = False
    try:
        if file_path.exists():
            os.remove(file_path)
            file_deleted = True
            logger.info(f"物理文件已删除: {file_path}")
        else:
            logger.warning(f"物理文件不存在，跳过删除: {file_path}")
            file_deleted = True
    except PermissionError as e:
        logger.warning(f"无权限删除物理文件，仅删除数据库记录: {file_path}, 错误: {str(e)}")
        file_deleted = True
    except Exception as e:
        logger.warning(f"删除物理文件失败，仅删除数据库记录: {file_path}, 错误: {str(e)}")
        file_deleted = True
    
    delete_success = delete_document(document_id)
    if not delete_success:
        raise BusinessException(code=1004, detail=f"文档ID: {document_id}")
    
    logger.info(f"文档删除成功: {document_id}")
    return success(
        data={"document_id": document_id, "file_deleted": file_deleted}, 
        message="文档删除成功"
    )

@router.get("/{document_id}/refine", summary="获取文档提炼结果")
async def get_document_refinement(document_id: str):
    """获取文档的内容提炼结果，包括层次结构和统计信息"""
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    try:
        filepath = doc_info.get('filepath')
        if not filepath or not os.path.exists(filepath):
            raise BusinessException(code=2003, detail="文档文件不存在")
        
        success, content = process_document(filepath)
        if not success:
            raise BusinessException(code=1002, detail="文档内容提取失败")
        
        refiner = ContentRefiner()
        result = refiner.refine_document(content, document_id)
        
        return success(data=result.to_dict(), message="文档提炼成功")
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"文档提炼失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"文档提炼失败: {str(e)}")

@router.get("/{document_id}/hierarchy", summary="获取文档层次结构")
async def get_document_hierarchy(document_id: str, format: str = Query("dict", description="输出格式: dict, flat, toc")):
    """获取文档的层次结构"""
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    try:
        filepath = doc_info.get('filepath')
        if not filepath or not os.path.exists(filepath):
            raise BusinessException(code=2003, detail="文档文件不存在")
        
        success, content = process_document(filepath)
        if not success:
            raise BusinessException(code=1002, detail="文档内容提取失败")
        
        refiner = ContentRefiner()
        result = refiner.refine_document(content, document_id)
        
        from utils.hierarchy_builder import HierarchyBuilder, HierarchyNode
        builder = HierarchyBuilder()
        hierarchy_root = HierarchyNode.from_dict(result.hierarchy)
        
        hierarchy_data = builder.export_hierarchy(hierarchy_root, format=format)
        
        return success(data=hierarchy_data, message="层次结构获取成功")
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"获取层次结构失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"获取层次结构失败: {str(e)}")

@router.get("/{document_id}/key-info", summary="获取文档关键信息")
async def get_document_key_info(document_id: str):
    """获取文档的关键信息摘要"""
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    try:
        filepath = doc_info.get('filepath')
        if not filepath or not os.path.exists(filepath):
            raise BusinessException(code=2003, detail="文档文件不存在")
        
        success, content = process_document(filepath)
        if not success:
            raise BusinessException(code=1002, detail="文档内容提取失败")
        
        refiner = ContentRefiner()
        key_info = refiner.extract_key_information(content)
        
        return success(data=key_info, message="关键信息提取成功")
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"关键信息提取失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"关键信息提取失败: {str(e)}")


class ReChunkRequest(BaseModel):
    use_refiner: bool = True


@router.post("/{document_id}/rechunk", summary="重新分片文档")
async def rechunk_document(document_id: str, request: ReChunkRequest = ReChunkRequest()):
    """对文档进行重新分片，删除旧分片并重新生成"""
    doc_info = get_document_info(document_id)
    if not doc_info:
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    
    try:
        success = re_chunk_document(document_id, use_refiner=request.use_refiner)
        if not success:
            raise BusinessException(code=1003, detail="重新分片失败")
        
        chunk_status = check_document_chunks(document_id)
        return success(data=chunk_status, message="文档重新分片成功")
    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"重新分片失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"重新分片失败: {str(e)}")


@router.get("/{document_id}/chunk-status", summary="获取文档分片状态")
async def get_chunk_status(document_id: str):
    """检查文档的分片状态"""
    chunk_status = check_document_chunks(document_id)
    if not chunk_status.get('exists'):
        raise BusinessException(code=1001, detail=f"文档ID: {document_id}")
    return success(data=chunk_status, message="获取分片状态成功")


class BatchReChunkRequest(BaseModel):
    document_ids: List[str]
    use_refiner: bool = True


@router.post("/batch/rechunk", summary="批量重新分片文档")
async def batch_rechunk_documents(request: BatchReChunkRequest):
    """批量对文档进行重新分片"""
    results = []
    for doc_id in request.document_ids:
        try:
            success = re_chunk_document(doc_id, use_refiner=request.use_refiner)
            results.append({
                "document_id": doc_id,
                "success": success
            })
        except Exception as e:
            logger.error(f"批量重新分片失败 {doc_id}: {str(e)}")
            results.append({
                "document_id": doc_id,
                "success": False,
                "error": str(e)
            })
    
    success_count = sum(1 for r in results if r['success'])
    return success(data={
        "results": results,
        "total": len(results),
        "success_count": success_count
    }, message=f"批量重新分片完成，成功 {success_count}/{len(results)}")
