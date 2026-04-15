import os
import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File, Query, Depends, Form
from fastapi.responses import FileResponse
from typing import List
from pydantic import BaseModel
import logging

from app.services.document_service import DocumentService
from app.services.category_service import category_service
from app.services.errors import AppServiceError
from app.services.organization_service import organization_service
from api import success, paginated, BusinessException
from api.dependencies import require_authenticated_user

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

logger = logging.getLogger(__name__)

router = APIRouter()
document_service = DocumentService()


def _directory_name_maps() -> tuple[dict[str, str], dict[str, str]]:
    departments = organization_service.store.list_departments()
    categories = category_service.store.list_business_categories()
    department_map = {
        str(item.get("id") or ""): str(item.get("name") or "")
        for item in departments
        if item.get("id")
    }
    category_map = {
        str(item.get("id") or ""): str(item.get("name") or "")
        for item in categories
        if item.get("id")
    }
    return department_map, category_map


def _build_document_response(doc_info: dict) -> dict:
    department_map, category_map = _directory_name_maps()
    owner_department_id = doc_info.get("owner_department_id")
    business_category_id = doc_info.get("business_category_id")
    return {
        "id": doc_info.get("id"),
        "filename": doc_info.get("filename"),
        "file_type": doc_info.get("file_type"),
        "preview_content": doc_info.get("preview_content", "")[:500],
        "full_content_length": doc_info.get("full_content_length", 0),
        "created_at_iso": doc_info.get("created_at_iso"),
        "classification_result": doc_info.get("classification_result"),
        "file_available": doc_info.get("file_available", False),
        "extraction_status": doc_info.get("extraction_status"),
        "parser_name": doc_info.get("parser_name"),
        "visibility_scope": doc_info.get("visibility_scope", "department"),
        "owner_department_id": owner_department_id,
        "owner_department_name": doc_info.get("owner_department_name")
        or department_map.get(str(owner_department_id or "")),
        "shared_department_ids": list(doc_info.get("shared_department_ids") or []),
        "business_category_id": business_category_id,
        "business_category_name": doc_info.get("business_category_name")
        or category_map.get(str(business_category_id or "")),
        "role_restriction": doc_info.get("role_restriction"),
        "is_public_restricted": bool(doc_info.get("is_public_restricted", False)),
        "confidentiality_level": doc_info.get("confidentiality_level", "internal"),
        "document_status": doc_info.get("document_status", "draft"),
    }


@router.post("/upload", summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    visibility_scope: str = Form("department"),
    owner_department_id: str | None = Form(None),
    shared_department_ids: str = Form(default="[]"),
    business_category_id: str | None = Form(None),
    role_restriction: str | None = Form(None),
    confidentiality_level: str = Form("internal"),
    document_status: str = Form("draft"),
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        parsed_shared_department_ids: List[str] = []
        try:
            parsed = json.loads(shared_department_ids or "[]")
            if not isinstance(parsed, list):
                raise AppServiceError(2001, "shared_department_ids 必须是 JSON 数组字符串")
            parsed_shared_department_ids = [str(item).strip() for item in parsed if str(item).strip()]
        except AppServiceError:
            raise
        except Exception:
            raise AppServiceError(2001, "shared_department_ids 必须是 JSON 数组字符串")

        derived_is_public_restricted = (
            visibility_scope == "public"
            and bool(parsed_shared_department_ids or role_restriction)
        )
        governance_metadata = {
            "visibility_scope": visibility_scope,
            "owner_department_id": owner_department_id,
            "shared_department_ids": parsed_shared_department_ids,
            "business_category_id": business_category_id,
            "role_restriction": role_restriction,
            "is_public_restricted": derived_is_public_restricted,
            "confidentiality_level": confidentiality_level,
            "document_status": document_status,
        }
        # 直接传递文件流对象，避免一次性读入内存（支持大文件）
        doc_info = document_service.upload(
            file.filename,
            file.file,
            current_user=current_user,
            governance_metadata=governance_metadata,
        )
        return success(data=_build_document_response(doc_info), message="文档上传成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

@router.get("/", summary="获取所有文档列表")
async def get_document_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=500, description="每页数量"),
    current_user: dict = Depends(require_authenticated_user),
):
    page_data = document_service.list_documents(page, page_size, current_user=current_user)
    items = [_build_document_response(doc) for doc in page_data["items"]]
    return paginated(items=items, total=page_data["total"], page=page, page_size=page_size)


@router.get("/{document_id}", summary="获取文档详情")
async def get_document_detail(document_id: str, current_user: dict = Depends(require_authenticated_user)):
    try:
        doc_info = document_service.get_document(document_id, current_user=current_user)
        return success(data=_build_document_response(doc_info))
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/{document_id}/content", summary="获取文档内容与分段")
async def get_document_content(document_id: str, current_user: dict = Depends(require_authenticated_user)):
    try:
        payload = document_service.get_document_payload(document_id, current_user=current_user)
        return success(data=payload)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/{document_id}/reader", summary="获取文档阅读器文本与高亮命中")
async def get_document_reader(
    document_id: str,
    query: str = "",
    anchor_block_id: str | None = None,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        payload = document_service.get_reader_payload(
            document_id,
            query=query,
            anchor_block_id=anchor_block_id,
            current_user=current_user,
        )
        return success(data=payload)
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


@router.get("/{document_id}/file", summary="下载/预览文档原文件")
async def get_document_file(document_id: str, current_user: dict = Depends(require_authenticated_user)):
    try:
        doc_info = document_service.get_document(document_id, current_user=current_user)
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


async def delete_document_api(document_id: str):
    try:
        result = document_service.delete_document(document_id)
        return success(data=result, message="文档删除成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)

class ReChunkRequest(BaseModel):
    use_refiner: bool = True


class UpdateDocumentRequest(BaseModel):
    visibility_scope: str | None = None
    owner_department_id: str | None = None
    shared_department_ids: List[str] | None = None
    business_category_id: str | None = None
    role_restriction: str | None = None
    is_public_restricted: bool | None = None
    confidentiality_level: str | None = None
    document_status: str | None = None


@router.patch("/{document_id}", summary="更新文档治理元数据")
async def update_document_metadata(
    document_id: str,
    request: UpdateDocumentRequest,
    current_user: dict = Depends(require_authenticated_user),
):
    try:
        updated_doc = document_service.update_document_metadata(
            document_id,
            request.model_dump(exclude_unset=True),
            current_user=current_user,
        )
        return success(data=_build_document_response(updated_doc), message="文档元数据更新成功")
    except AppServiceError as exc:
        raise BusinessException(code=exc.code, detail=exc.detail)


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
