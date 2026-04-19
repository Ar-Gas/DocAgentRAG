import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import FileResponse
from typing import List
from pydantic import BaseModel

from app.core.logger import logger
from app.services.document_service import DocumentService
from app.services.errors import AppServiceError
from api import success, paginated, BusinessException

_CONTENT_TYPES = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc":  "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".txt":  "text/plain; charset=utf-8",
    ".md":   "text/plain; charset=utf-8",
}

router = APIRouter()
document_service = DocumentService()


def _build_document_response(doc_info: dict) -> dict:
    payload = doc_info if isinstance(doc_info, dict) else {}
    return {
        "id": payload.get("id"),
        "filename": payload.get("filename"),
        "file_type": payload.get("file_type"),
        "preview_content": str(payload.get("preview_content", "") or "")[:500],
        "full_content_length": payload.get("full_content_length", 0),
        "created_at_iso": payload.get("created_at_iso"),
        "classification_result": payload.get("classification_result"),
        "classification_id": payload.get("classification_id"),
        "classification_path": payload.get("classification_path"),
        "classification_score": payload.get("classification_score"),
        "classification_source": payload.get("classification_source"),
        "file_available": payload.get("file_available", False),
        "extraction_status": payload.get("extraction_status"),
        "parser_name": payload.get("parser_name"),
        "ingest_status": payload.get("ingest_status"),
        "ingest_error": payload.get("ingest_error"),
        "lightrag_track_id": payload.get("lightrag_track_id"),
        "lightrag_doc_id": payload.get("lightrag_doc_id"),
        "last_status_sync_at": payload.get("last_status_sync_at"),
    }

@router.post("/upload", summary="上传文档")
async def upload_document(file: UploadFile = File(...)):
    try:
        # 直接传递文件流对象，避免一次性读入内存（支持大文件）
        doc_info = document_service.upload(file.filename, file.file)
        return success(data=_build_document_response(doc_info), message="文档上传成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/", summary="获取所有文档列表")
async def get_document_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=500, description="每页数量")
):
    logger.info("query_documents_api page={} page_size={}", page, page_size)
    try:
        page_data = document_service.list_documents(page, page_size)
        items = [_build_document_response(doc) for doc in page_data.get("items", [])]
        return paginated(items=items, total=page_data.get("total", 0), page=page, page_size=page_size)
    except Exception as exc:
        logger.opt(exception=exc).error("query_documents_api_failed page={} page_size={}", page, page_size)
        return paginated(items=[], total=0, page=page, page_size=page_size)


@router.get("/stats", summary="获取文档列表统计信息")
async def get_document_stats():
    logger.info("query_document_stats_api")
    try:
        return success(data=document_service.stats())
    except Exception as exc:
        logger.opt(exception=exc).error("query_document_stats_api_failed")
        return success(data={"total": 0, "categorized": 0, "uncategorized": 0})

@router.get("/{document_id}", summary="获取文档详情")
async def get_document_detail(document_id: str):
    try:
        doc_info = document_service.get_document(document_id)
        return success(data=_build_document_response(doc_info))
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/{document_id}/content", summary="获取文档内容与分段")
async def get_document_content(document_id: str):
    try:
        payload = document_service.get_document_payload(document_id)
        return success(data=payload)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/{document_id}/reader", summary="获取文档阅读器文本与高亮命中")
async def get_document_reader(
    document_id: str,
    query: str = "",
    anchor_block_id: str | None = None,
):
    try:
        payload = document_service.get_reader_payload(
            document_id,
            query=query,
            anchor_block_id=anchor_block_id,
        )
        return success(data=payload)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/{document_id}/file", summary="下载/预览文档原文件")
async def get_document_file(document_id: str):
    try:
        doc_info = document_service.get_document(document_id)
        filepath = doc_info.get("filepath") or doc_info.get("path") or ""
        if not filepath or doc_info.get("file_available") is False or not os.path.exists(filepath):
            raise BusinessException(code=1001, detail="文件不在服务器上，可能已被移动或删除")
        filename = doc_info.get("filename", Path(filepath).name)
        ext = Path(filepath).suffix.lower()
        content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
        quoted_filename = quote(filename)
        return FileResponse(
            path=filepath,
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{quoted_filename}"},
        )
    except BusinessException:
        raise
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.delete("/{document_id}", summary="删除文档")
async def delete_document_api(document_id: str):
    try:
        result = document_service.delete_document(document_id)
        return success(data=result, message="文档删除成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.post("/{document_id}/retry-ingest", summary="重试导入 LightRAG")
async def retry_document_ingest(document_id: str):
    try:
        result = document_service.retry_ingest(document_id)
        return success(data=_build_document_response(result), message="文档已重新提交导入队列")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

class ReChunkRequest(BaseModel):
    use_refiner: bool = True


@router.post("/{document_id}/rechunk", summary="重新分片文档")
async def rechunk_document(document_id: str, request: ReChunkRequest = ReChunkRequest()):
    try:
        chunk_status = document_service.rechunk(document_id, request.use_refiner)
        return success(data=chunk_status, message="文档重新分片成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)
    except Exception as e:
        logger.error(f"重新分片失败: {str(e)}")
        raise BusinessException(code=1005, detail=f"重新分片失败: {str(e)}")


@router.get("/{document_id}/chunk-status", summary="获取文档分片状态")
async def get_chunk_status(document_id: str):
    try:
        chunk_status = document_service.get_chunk_status(document_id)
        return success(data=chunk_status, message="获取分片状态成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


class BatchReChunkRequest(BaseModel):
    document_ids: List[str]
    use_refiner: bool = True


@router.post("/batch/rechunk", summary="批量重新分片文档")
async def batch_rechunk_documents(request: BatchReChunkRequest):
    result = document_service.batch_rechunk(request.document_ids, request.use_refiner)
    return success(
        data=result,
        message=f"批量重新分片完成，成功 {result['success_count']}/{result['total']}"
    )
