"""Admin API - 系统管理端点"""
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
import httpx

from app.core.logger import logger
from app.services.document_audit_service import DocumentAuditService
from app.services.document_service import DocumentService
from app.services.local_embedding_runtime import LocalEmbeddingRuntime
from app.services.observability_service import ObservabilityService
from api import success, BusinessException
from config import LIGHTRAG_BASE_URL

router = APIRouter()
obs_service = ObservabilityService()
document_audit_service = DocumentAuditService()
document_service = DocumentService()
local_embedding_runtime = LocalEmbeddingRuntime()

LIGHTRAG_WEBUI_PROXY_PREFIX = "/api/v1/admin/lightrag/webui"
LIGHTRAG_APP_PROXY_PREFIX = "/api/v1/admin/lightrag/app"


class LocalOnlyBatchImportRequest(BaseModel):
    limit: int = 100
    concurrency: int = 1
    interval_seconds: float = 0.5
    include_failed: bool = False


def _rewrite_lightrag_branding(raw_text: str) -> str:
    return (
        raw_text
        .replace("https://github.com/HKUDS/LightRAG", "#")
        .replace("LightRAG", "DocAgent Studio")
        .replace("Lightrag", "DocAgent Studio")
    )


def _sanitize_lightrag_webui_html(raw_html: str) -> str:
    sanitized = _rewrite_lightrag_branding(raw_html)
    sanitized = sanitized.replace(
        'src="/webui/',
        f'src="{LIGHTRAG_WEBUI_PROXY_PREFIX}/',
    ).replace(
        'href="/webui/',
        f'href="{LIGHTRAG_WEBUI_PROXY_PREFIX}/',
    ).replace(
        'src="logo.svg"',
        'src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="',
    ).replace(
        'href="favicon.png"',
        'href="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="',
    )
    injection = """
<style>
  a[href*="github.com"],
  a[href*="HKUDS"],
  a[href="#"],
  [class*="footer"],
  [id*="footer"] {
    display: none !important;
  }
</style>
""".strip()
    if "</head>" in sanitized:
        sanitized = sanitized.replace("</head>", f"{injection}</head>", 1)
    return sanitized


def _sanitize_lightrag_webui_javascript(raw_javascript: str) -> str:
    sanitized = _rewrite_lightrag_branding(raw_javascript)
    return (
        sanitized
        .replace('const Fh=""', f'const Fh="{LIGHTRAG_APP_PROXY_PREFIX}"')
        .replace('Fh="",', f'Fh="{LIGHTRAG_APP_PROXY_PREFIX}",')
        .replace('dW="/webui/"', f'dW="{LIGHTRAG_WEBUI_PROXY_PREFIX}/"')
    )


async def _proxy_lightrag_webui_request(
    *,
    base_path: str = "webui",
    path: str = "",
    query: str = "",
    method: str = "GET",
    body: bytes = b"",
    content_type: str | None = None,
):
    root_base_url = LIGHTRAG_BASE_URL.rstrip("/")
    normalized_base_path = base_path.strip("/")
    normalized_path = path.lstrip("/")
    if normalized_base_path:
        upstream_url = (
            f"{root_base_url}/{normalized_base_path}/{normalized_path}"
            if normalized_path
            else f"{root_base_url}/{normalized_base_path}/"
        )
    else:
        upstream_url = (
            f"{root_base_url}/{normalized_path}"
            if normalized_path
            else f"{root_base_url}/"
        )
    if query:
        upstream_url = f"{upstream_url}?{query}"

    headers = {}
    if content_type:
        headers["content-type"] = content_type

    async with httpx.AsyncClient(timeout=60.0) as client:
        return await client.request(
            method=method,
            url=upstream_url,
            headers=headers,
            content=body or None,
        )


def _requires_local_embedding_preflight(path: str, method: str) -> bool:
    normalized_path = (path or "").strip("/")
    normalized_method = (method or "GET").upper()
    if normalized_method != "POST":
        return False
    return normalized_path in {"documents/upload", "documents/reprocess_failed"}


@router.get("/stats", summary="获取系统统计")
async def get_system_stats():
    """获取系统运行统计信息"""
    try:
        stats = obs_service.get_system_stats()
        return success(data=stats, message="获取统计成功")

    except Exception as e:
        logger.error(f"获取统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/llm-stats", summary="获取 LLM 调用统计")
async def get_llm_stats():
    """获取 LLM token 用量统计"""
    try:
        stats = obs_service.get_llm_stats()
        return success(data=stats, message="获取 LLM 统计成功")

    except Exception as e:
        logger.error(f"获取 LLM 统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/cache-stats", summary="获取缓存统计")
async def get_cache_stats():
    """获取缓存使用统计"""
    try:
        stats = obs_service.get_cache_stats()
        return success(data=stats, message="获取缓存统计成功")

    except Exception as e:
        logger.error(f"获取缓存统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/reset-stats", summary="重置统计")
async def reset_stats():
    """重置所有统计信息"""
    try:
        obs_service.reset_stats()
        return success(message="统计已重置")

    except Exception as e:
        logger.error(f"重置统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/document-audit", summary="获取文档审计信息")
async def get_document_audit():
    try:
        payload = await document_audit_service.audit()
        return success(data=payload, message="获取文档审计成功")
    except Exception as e:
        logger.error(f"获取文档审计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/document-import/local-only", summary="启动 local_only 文档批量导入")
async def start_local_only_batch_import(request: LocalOnlyBatchImportRequest):
    try:
        registered = document_audit_service.register_local_only_documents()
        payload = document_service.start_local_only_batch_import(
            limit=request.limit,
            concurrency=request.concurrency,
            interval_seconds=request.interval_seconds,
            include_failed=request.include_failed,
        )
        payload["registered_local_only_documents"] = registered
        return success(data=payload, message="已启动 local_only 文档批量导入")
    except Exception as e:
        logger.error(f"启动 local_only 批量导入失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/document-import/local-only", summary="查询 local_only 文档批量导入状态")
async def get_local_only_batch_import_status():
    try:
        return success(data=document_service.get_batch_import_status(), message="获取批量导入状态成功")
    except Exception as e:
        logger.error(f"获取 local_only 批量导入状态失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.api_route("/lightrag/webui", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/lightrag/webui/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_lightrag_webui_root(request: Request):
    return await proxy_lightrag_webui_path("", request)


@router.api_route("/lightrag/webui/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_lightrag_webui_path(path: str, request: Request):
    try:
        query = request.url.query
        method = request.method
        body = b""
        if method.upper() not in {"GET", "HEAD"}:
            body = await request.body()
        content_type = request.headers.get("content-type")
        upstream = await _proxy_lightrag_webui_request(
            base_path="webui",
            path=path,
            query=query,
            method=method,
            body=body,
            content_type=content_type,
        )

        media_type = upstream.headers.get("content-type", "text/plain")
        content = upstream.content
        if "text/html" in media_type:
            content = _sanitize_lightrag_webui_html(
                upstream.content.decode("utf-8", errors="ignore")
            ).encode("utf-8")
        elif "javascript" in media_type or path.endswith(".js"):
            content = _sanitize_lightrag_webui_javascript(
                upstream.content.decode("utf-8", errors="ignore")
            ).encode("utf-8")

        passthrough_headers = {}
        if upstream.headers.get("cache-control"):
            passthrough_headers["cache-control"] = upstream.headers["cache-control"]

        return Response(
            content=content,
            status_code=upstream.status_code,
            media_type=media_type.split(";", 1)[0],
            headers=passthrough_headers,
        )
    except Exception as e:
        logger.error(f"代理 LightRAG WebUI 失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.api_route("/lightrag/app", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/lightrag/app/", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_lightrag_app_root(request: Request):
    return await proxy_lightrag_app_path("", request)


@router.api_route("/lightrag/app/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_lightrag_app_path(path: str, request: Request):
    try:
        query = request.url.query
        method = request.method
        body = b""
        if method.upper() not in {"GET", "HEAD"}:
            body = await request.body()
        if _requires_local_embedding_preflight(path, method):
            await local_embedding_runtime.ensure_ready()
        content_type = request.headers.get("content-type")
        upstream = await _proxy_lightrag_webui_request(
            base_path="",
            path=path,
            query=query,
            method=method,
            body=body,
            content_type=content_type,
        )

        media_type = upstream.headers.get("content-type", "text/plain")
        passthrough_headers = {}
        if upstream.headers.get("cache-control"):
            passthrough_headers["cache-control"] = upstream.headers["cache-control"]

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=media_type.split(";", 1)[0],
            headers=passthrough_headers,
        )
    except Exception as e:
        logger.error(f"代理 LightRAG 应用接口失败: {str(e)}")
        raise BusinessException(500, detail=str(e))
