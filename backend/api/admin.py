"""Admin API - 系统管理端点"""
import json
import os
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

from app.core.logger import logger
from app.services.classification_service import ClassificationService
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
classification_service = ClassificationService()
local_embedding_runtime = LocalEmbeddingRuntime()

LIGHTRAG_WEBUI_PROXY_PREFIX = "/api/v1/admin/lightrag/webui"
LIGHTRAG_APP_PROXY_PREFIX = "/api/v1/admin/lightrag/app"
LIGHTRAG_GRAPH_PROXY_MAX_MAX_NODES = max(
    int(
        os.getenv(
            "LIGHTRAG_GRAPH_PROXY_MAX_MAX_NODES",
            os.getenv("LIGHTRAG_GRAPH_PROXY_MIN_MAX_NODES", "5000"),
        )
        or "5000"
    ),
    1,
)
LIGHTRAG_STREAM_PROXY_TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=None,
    write=300.0,
    pool=300.0,
)
LIGHTRAG_LAZY_GRAPH_QUERY_LABEL = ""
LIGHTRAG_LAZY_GRAPH_DEFAULT_MAX_NODES = 300


class LocalOnlyBatchImportRequest(BaseModel):
    limit: int = 100
    concurrency: int = 1
    interval_seconds: float = 0.5
    include_failed: bool = False


class LocalIndexBackfillRequest(BaseModel):
    limit: int = 100
    include_failed: bool = False
    build_block_index: bool = False


class BatchClassificationRequest(BaseModel):
    limit: int = 100
    include_needs_review: bool = True
    force: bool = False


def _rewrite_lightrag_branding(raw_text: str) -> str:
    return (
        raw_text
        .replace("https://github.com/HKUDS/LightRAG", "#")
        .replace("LightRAG", "DocAgent Studio")
        .replace("Lightrag", "DocAgent Studio")
    )


def _build_lightrag_lazy_graph_bootstrap_script() -> str:
    return f"""
<script data-docagent-lazy-graph-bootstrap>
  (() => {{
    const storageKey = "settings-storage";
    const defaultQueryLabel = {json.dumps(LIGHTRAG_LAZY_GRAPH_QUERY_LABEL)};
    const defaultMaxNodes = {LIGHTRAG_LAZY_GRAPH_DEFAULT_MAX_NODES};
    try {{
      const raw = window.localStorage.getItem(storageKey);
      const payload = raw ? JSON.parse(raw) : {{}};
      const safePayload = payload && typeof payload === "object" ? payload : {{}};
      const rawState = safePayload.state;
      const state = {{}};
      let changed = false;

      if (rawState && typeof rawState === "object") {{
        Object.assign(state, rawState);
      }} else if (typeof rawState === "string") {{
        try {{
          const parsedState = JSON.parse(rawState);
          if (parsedState && typeof parsedState === "object") {{
            Object.assign(state, parsedState);
          }} else {{
            changed = true;
          }}
        }} catch (_parseStateError) {{
          changed = true;
        }}
      }} else if (typeof rawState !== "undefined") {{
        changed = true;
      }}

      const currentQueryLabel = typeof state.queryLabel === "string" ? state.queryLabel : "";
      if (!currentQueryLabel || currentQueryLabel === "*") {{
        if (state.queryLabel !== defaultQueryLabel) {{
          state.queryLabel = defaultQueryLabel;
          changed = true;
        }}
      }}

      const isBlankMaxNodes = typeof state.graphMaxNodes === "string" && !state.graphMaxNodes.trim();
      const currentMaxNodes = Number(state.graphMaxNodes);
      if (isBlankMaxNodes || !Number.isFinite(currentMaxNodes) || currentMaxNodes > defaultMaxNodes) {{
        if (state.graphMaxNodes !== defaultMaxNodes) {{
          state.graphMaxNodes = defaultMaxNodes;
          changed = true;
        }}
      }}

      if (changed) {{
        safePayload.state = typeof rawState === "string" ? JSON.stringify(state) : state;
        window.localStorage.setItem(storageKey, JSON.stringify(safePayload));
      }}
    }} catch (_error) {{
      // Fail open to avoid breaking startup.
    }}
  }})();
</script>
""".strip()


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
    lazy_graph_bootstrap_injection = _build_lightrag_lazy_graph_bootstrap_script()
    injection = """
<style data-docagent-hide-api-tab>
  a[href*="github.com"],
  a[href*="HKUDS"],
  a[href="#"],
  [class*="footer"],
  [id*="footer"],
  iframe.api-docs-iframe,
  [class*="api-docs"],
  [id*="api-docs"] {
    display: none !important;
  }
</style>
<script data-docagent-hide-api-tab>
  (() => {
    const hideApiEntry = () => {
      const candidates = Array.from(document.querySelectorAll('a, button, [role="tab"], [data-state], [class]'));
      for (const node of candidates) {
        const text = (node.textContent || '').trim().toLowerCase();
        const href = (node.getAttribute && (node.getAttribute('href') || node.getAttribute('to') || '')) || '';
        if (text === 'api' || href.includes('api')) {
          node.style.display = 'none';
          node.setAttribute('aria-hidden', 'true');
        }
      }
    };
    hideApiEntry();
    new MutationObserver(hideApiEntry).observe(document.documentElement, { childList: true, subtree: true });
  })();
</script>
""".strip()
    if "</head>" in sanitized:
        sanitized = sanitized.replace(
            "</head>",
            f"{lazy_graph_bootstrap_injection}\n{injection}</head>",
            1,
        )
    return sanitized


def _sanitize_lightrag_webui_javascript(raw_javascript: str) -> str:
    sanitized = _rewrite_lightrag_branding(raw_javascript)
    sanitized = (
        sanitized
        .replace('const Fh=""', f'const Fh="{LIGHTRAG_APP_PROXY_PREFIX}"')
        .replace('Fh="",', f'Fh="{LIGHTRAG_APP_PROXY_PREFIX}",')
        .replace('dW="/webui/"', f'dW="{LIGHTRAG_WEBUI_PROXY_PREFIX}/"')
    )
    sanitized = sanitized.replace(
        "visibleTabs:r",
        "visibleTabs:{...r,api:!1}",
    ).replace(
        "visibleTabs:r,",
        "visibleTabs:{...r,api:!1},",
    )
    if "api:!1" not in sanitized and (
        "visibleTabs" in sanitized
        or "apiSite" in sanitized
        or "header.api" in sanitized
        or LIGHTRAG_APP_PROXY_PREFIX in sanitized
        or LIGHTRAG_WEBUI_PROXY_PREFIX in sanitized
    ):
        sanitized = f"{sanitized}\n;window.__DOCAGENT_HIDE_LIGHTRAG_API_TAB__={{api:!1}};"
    sanitized = sanitized.replace(
        'R?.is_truncated&&Kt.info(e("graphPanel.dataIsTruncated","Graph data is truncated to Max Nodes"))',
        'R?.is_truncated&&console.info("DocAgent graph truncated")',
    )
    return sanitized


def _build_lightrag_upstream_url(*, base_path: str = "webui", path: str = "", query: str = "") -> str:
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
    return upstream_url


async def _proxy_lightrag_webui_request(
    *,
    base_path: str = "webui",
    path: str = "",
    query: str = "",
    method: str = "GET",
    body: bytes = b"",
    content_type: str | None = None,
):
    upstream_url = _build_lightrag_upstream_url(base_path=base_path, path=path, query=query)
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


async def _proxy_lightrag_stream_request(
    *,
    path: str = "",
    query: str = "",
    method: str = "GET",
    body: bytes = b"",
    content_type: str | None = None,
):
    upstream_url = _build_lightrag_upstream_url(base_path="", path=path, query=query)
    headers = {}
    if content_type:
        headers["content-type"] = content_type

    client = httpx.AsyncClient(timeout=LIGHTRAG_STREAM_PROXY_TIMEOUT)
    request = client.build_request(
        method=method,
        url=upstream_url,
        headers=headers,
        content=body or None,
    )
    upstream = await client.send(request, stream=True)

    async def _stream_bytes():
        try:
            async for chunk in upstream.aiter_raw():
                if chunk:
                    yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    media_type = upstream.headers.get("content-type", "application/octet-stream")
    passthrough_headers = {}
    for header_name in ("cache-control", "x-accel-buffering", "content-disposition"):
        if upstream.headers.get(header_name):
            passthrough_headers[header_name] = upstream.headers[header_name]

    return StreamingResponse(
        _stream_bytes(),
        status_code=upstream.status_code,
        media_type=media_type.split(";", 1)[0],
        headers=passthrough_headers,
    )


def _requires_local_embedding_preflight(path: str, method: str) -> bool:
    normalized_path = (path or "").strip("/")
    normalized_method = (method or "GET").upper()
    if normalized_method != "POST":
        return False
    return normalized_path in {"documents/upload", "documents/reprocess_failed"}


def _is_streaming_lightrag_path(path: str, method: str) -> bool:
    normalized_path = (path or "").strip("/")
    normalized_method = (method or "GET").upper()
    return normalized_method == "POST" and normalized_path == "query/stream"


def _normalize_lightrag_app_query(path: str, query: str) -> str:
    normalized_path = (path or "").strip("/")
    if normalized_path != "graphs":
        return query

    items = parse_qsl(query, keep_blank_values=True)
    payload = {key: value for key, value in items}
    raw_max_nodes = str(payload.get("max_nodes", "")).strip()
    if not raw_max_nodes:
        return query

    try:
        max_nodes = int(raw_max_nodes)
    except ValueError:
        return query

    # Respect the UI's requested graph size and only apply a hard ceiling to
    # prevent accidental oversized graph fetches from hanging the workbench.
    if max_nodes > LIGHTRAG_GRAPH_PROXY_MAX_MAX_NODES:
        payload["max_nodes"] = str(LIGHTRAG_GRAPH_PROXY_MAX_MAX_NODES)
        return urlencode(payload)

    return query


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


@router.post("/document-index/backfill", summary="批量补齐本地文档阅读索引")
async def backfill_local_document_index(request: LocalIndexBackfillRequest):
    try:
        payload = document_service.backfill_local_index(
            limit=request.limit,
            include_failed=request.include_failed,
            build_block_index=request.build_block_index,
        )
        return success(data=payload, message="本地文档阅读索引补齐完成")
    except Exception as e:
        logger.error(f"补齐本地文档阅读索引失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/classification/backfill", summary="批量补齐可分类文档的 taxonomy 分类")
async def batch_classify_ready_documents(request: BatchClassificationRequest):
    try:
        payload = classification_service.batch_classify_ready_documents(
            limit=request.limit,
            include_needs_review=request.include_needs_review,
            force=request.force,
        )
        return success(data=payload, message="文档分类补齐完成")
    except Exception as e:
        logger.error(f"批量补齐文档分类失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/runtime/health", summary="获取运行时健康状态")
async def get_runtime_health():
    try:
        embedding = await local_embedding_runtime.health()
        payload = {
            "dependencies": {
                "local_embedding": {
                    "status": embedding.get("status"),
                    "liveness": embedding.get(
                        "liveness",
                        "up" if embedding.get("status") != "unhealthy" else "down",
                    ),
                    "readiness": embedding.get(
                        "readiness",
                        "ready" if embedding.get("ready") else "unready",
                    ),
                    "detail": embedding.get("detail"),
                }
            },
            **document_service.get_runtime_health(),
        }
        return success(data=payload, message="获取运行时健康成功")
    except Exception as e:
        logger.error(f"获取运行时健康失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.post("/runtime/documents/{document_id}/retry-rag", summary="重试文档 RAG 入库阶段")
async def retry_rag_stage(document_id: str):
    try:
        payload = document_service.retry_rag_stage(document_id)
        return success(data=payload, message="已重新加入 RAG 阶段队列")
    except Exception as e:
        logger.error(f"重试 RAG 阶段失败: {str(e)}")
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
        normalized_path = (path or "").strip("/")
        query = _normalize_lightrag_app_query(normalized_path, request.url.query)
        method = request.method
        body = b""
        if method.upper() not in {"GET", "HEAD"}:
            body = await request.body()
        if _requires_local_embedding_preflight(normalized_path, method):
            await local_embedding_runtime.ensure_ready()
        content_type = request.headers.get("content-type")
        if _is_streaming_lightrag_path(normalized_path, method):
            return await _proxy_lightrag_stream_request(
                path=normalized_path,
                query=query,
                method=method,
                body=body,
                content_type=content_type,
            )
        upstream = await _proxy_lightrag_webui_request(
            base_path="",
            path=normalized_path,
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
