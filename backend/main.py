from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import os
from pathlib import Path

from config import (
    API_PREFIX,
    BASE_DIR,
    DATA_DIR,
    DOC_DIR,
    FILE_TYPE_DIRS,
    DOUBAO_API_KEY,
    DOUBAO_DEFAULT_LLM_MODEL,
)
import config as _config
from api import (
    router as api_router,
    BusinessException,
    business_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)
from app.core.logger import RequestContextMiddleware, logger, setup_logging
from app.services.classification_service import ClassificationService
from app.services.document_audit_service import DocumentAuditService
from app.services.document_service import DocumentService
from app.services.lightrag_runtime import LightRAGRuntime
from app.services.local_embedding_runtime import LocalEmbeddingRuntime
setup_logging()


def _document_audit_service() -> DocumentAuditService:
    return DocumentAuditService()


def _frontend_dist_dir() -> Path:
    return BASE_DIR.parent / "frontend" / "docagent-frontend" / "dist"


def _serve_frontend_dist() -> bool:
    return _env_flag("DOCAGENT_SERVE_FRONTEND_DIST")


def sync_doubao_llm_availability(
    doubao_api_key: str,
    doubao_default_llm_model: str,
    config_module,
    logger_instance,
) -> bool:
    if not doubao_api_key:
        logger_instance.warning("未配置 DOUBAO_API_KEY，智能检索将降级为 hybrid 模式，分类功能不可用。")
        config_module.LLM_AVAILABLE = False
        return False

    config_module.LLM_AVAILABLE = True
    logger_instance.info(f"LLM provider: Doubao, model: {doubao_default_llm_model}")
    return True


def _env_flag(*names: str) -> bool:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value.strip().lower() == "true"
    return False


def _startup_sync_enabled() -> bool:
    for name in ("DOCAGENT_STARTUP_SYNC_ENABLED",):
        value = os.getenv(name)
        if value is not None:
            return value.strip().lower() == "true"
    return True


def _load_cors_settings() -> tuple[list[str], bool]:
    origins_env = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    if not origins:
        origins = ["*"]
    allow_credentials = "*" not in origins
    return origins, allow_credentials


def _load_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return max(int(raw_value), minimum)
    except ValueError:
        logger.warning("invalid integer env {}={}, fallback={}", name, raw_value, default)
        return default


def _load_float_env(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return max(float(raw_value), minimum)
    except ValueError:
        logger.warning("invalid float env {}={}, fallback={}", name, raw_value, default)
        return default


def _build_uvicorn_options() -> dict:
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    default_workers = 1
    workers = 1 if dev_mode else _load_int_env("UVICORN_WORKERS", default_workers)
    return {
        "host": os.getenv("UVICORN_HOST", "0.0.0.0"),
        "port": _load_int_env("UVICORN_PORT", 6008),
        "reload": dev_mode,
        "workers": workers,
    }


async def refresh_document_audit_state(*, register_local_only: bool = True) -> dict:
    try:
        audit_service = _document_audit_service()
        registered_local_only_documents = 0
        if register_local_only:
            registered_local_only_documents = audit_service.register_local_only_documents()
        audit = await audit_service.audit()
        if register_local_only:
            audit["registered_local_only_documents"] = registered_local_only_documents
        return audit
    except Exception as exc:
        logger.warning("document audit failed: {}", exc)
        return {
            "status": "failed",
            "detail": str(exc),
            "registered_local_only_documents": 0,
            "lightrag": {"status": "unhealthy", "detail": str(exc)},
            "local_embedding": {"status": "unhealthy", "detail": str(exc)},
        }


async def ensure_internal_runtimes() -> dict:
    results = {}
    try:
        results["local_embedding"] = await LocalEmbeddingRuntime().ensure_ready()
    except Exception as exc:
        logger.warning("local embedding startup failed: {}", exc)
        results["local_embedding"] = {"status": "unhealthy", "detail": str(exc)}

    try:
        results["lightrag"] = await LightRAGRuntime().ensure_ready()
    except Exception as exc:
        logger.warning("LightRAG startup failed: {}", exc)
        results["lightrag"] = {"status": "unhealthy", "detail": str(exc)}

    return results


async def run_startup_reconciliation(
    *,
    document_service_factory=DocumentService,
    classification_service_factory=ClassificationService,
) -> dict:
    if not _startup_sync_enabled():
        return {"status": "disabled"}

    payload = {
        "status": "running",
        "local_index": None,
        "lightrag_recovery": None,
        "lightrag_ingest": None,
        "classification": None,
    }
    try:
        document_service = document_service_factory()
        local_index_limit = _load_int_env("DOCAGENT_STARTUP_LOCAL_INDEX_LIMIT", 100)
        lightrag_limit = _load_int_env("DOCAGENT_STARTUP_LIGHTRAG_LIMIT", 100)
        classification_limit = _load_int_env("DOCAGENT_STARTUP_CLASSIFICATION_LIMIT", 100)
        ingest_concurrency = _load_int_env("DOCAGENT_STARTUP_LIGHTRAG_CONCURRENCY", 1)
        ingest_interval = _load_float_env("DOCAGENT_STARTUP_LIGHTRAG_INTERVAL_SECONDS", 0.5)

        payload["local_index"] = await asyncio.to_thread(
            document_service.backfill_local_index,
            limit=local_index_limit,
            include_failed=False,
            build_block_index=False,
        )
        await asyncio.to_thread(
            document_service.reconcile_missing_lightrag_documents,
            limit=lightrag_limit,
        )
        payload["lightrag_recovery"] = await asyncio.to_thread(
            document_service.recover_stale_lightrag_queue,
        )
        document_service.start_local_only_batch_import(
            limit=lightrag_limit,
            concurrency=ingest_concurrency,
            interval_seconds=ingest_interval,
            include_failed=False,
        )
        await document_service.wait_for_batch_import()
        payload["lightrag_ingest"] = document_service.get_batch_import_status()

        classification_service = classification_service_factory()
        payload["classification"] = await asyncio.to_thread(
            classification_service.batch_classify_ready_documents,
            limit=classification_limit,
            include_needs_review=True,
            force=False,
        )
        payload["status"] = "completed"
        logger.info(
            "startup reconciliation completed local_index={} lightrag={} classification={}",
            payload.get("local_index"),
            payload.get("lightrag_ingest"),
            payload.get("classification"),
        )
        return payload
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
        logger.warning("startup reconciliation failed: {}", exc)
        return payload


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("办公文档智能分类与检索系统启动中...")
    logger.info("=" * 50)
    
    for dir_path in [DOC_DIR, DATA_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"确保目录存在：{dir_path}")
    
    for type_dir in FILE_TYPE_DIRS:
        type_path = DOC_DIR / type_dir
        type_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建文件类型目录：{type_path}")
    
    # 0.2 API Key 可用性检查
    sync_doubao_llm_availability(
        doubao_api_key=DOUBAO_API_KEY,
        doubao_default_llm_model=DOUBAO_DEFAULT_LLM_MODEL,
        config_module=_config,
        logger_instance=logger,
    )

    runtime_state = await ensure_internal_runtimes()
    app.state.runtime_state = runtime_state
    logger.info(
        "runtime state: local_embedding={} lightrag={}",
        (runtime_state.get("local_embedding") or {}).get("status", "unknown"),
        (runtime_state.get("lightrag") or {}).get("status", "unknown"),
    )

    audit = await refresh_document_audit_state(register_local_only=True)
    app.state.document_audit = audit
    logger.info(
        "document audit: sqlite={} local_files={} legacy_json={} untracked={} pending={} lightrag={} registered_local_only={}",
        audit.get("sqlite_documents", 0),
        audit.get("local_files", 0),
        audit.get("legacy_json_documents", 0),
        len(audit.get("untracked_local_files", [])),
        audit.get("pending_ingest_documents", 0),
        (audit.get("lightrag") or {}).get("status", "unknown"),
        audit.get("registered_local_only_documents", 0),
    )
    app.state.startup_reconciliation = {"status": "disabled"}
    if _startup_sync_enabled():
        app.state.startup_reconciliation = {"status": "scheduled"}

        async def _startup_reconciliation_runner() -> None:
            app.state.startup_reconciliation = {"status": "running"}
            app.state.startup_reconciliation = await run_startup_reconciliation()

        app.state.startup_reconciliation_task = asyncio.create_task(
            _startup_reconciliation_runner()
        )
    
    logger.info("=" * 50)
    logger.info("系统启动完成！")
    logger.info("=" * 50)
    
    yield
    
    logger.info("系统正在关闭...")

app = FastAPI(
    title="办公文档智能分类与检索系统",
    description="支持文档上传、智能分类、向量检索、扫描版PDF OCR等功能",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_exception_handler(BusinessException, business_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# 0.4 CORS 通过环境变量配置，生产环境应设置 ALLOWED_ORIGINS=https://yourdomain.com
ALLOWED_ORIGINS, ALLOW_CREDENTIALS = _load_cors_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(api_router, prefix=API_PREFIX)

frontend_dist = _frontend_dist_dir()
frontend_assets = frontend_dist / "assets"
if _serve_frontend_dist() and frontend_assets.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_assets)), name="frontend-assets")

# 2.2 兼容旧 /api 路径，307 临时重定向到 /api/v1（未来版本删除）
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def legacy_api_redirect(path: str, request: Request):
    # 防止 /api/v1/... 被误捕获后产生重定向循环
    if path.startswith("v1"):
        raise HTTPException(status_code=404, detail="Not Found")
    new_url = str(request.url).replace("/api/", "/api/v1/", 1)
    return RedirectResponse(url=new_url, status_code=307)


@app.get("/", summary="根路径")
async def root():
    index_path = _frontend_dist_dir() / "index.html"
    if _serve_frontend_dist() and index_path.exists():
        return FileResponse(index_path)
    return {
        "message": "办公文档智能分类与检索系统后端API",
        "version": "1.0.0",
        "api_prefix": API_PREFIX,
        "docs": "/docs"
    }


@app.head("/", summary="根路径探活")
async def root_head():
    return Response(status_code=200)

@app.get("/health", summary="健康检查")
async def health_check():
    audit = await refresh_document_audit_state(register_local_only=False)
    app.state.document_audit = audit
    lightrag_status = (audit.get("lightrag") or {}).get("status", "unknown")
    local_embedding_status = (audit.get("local_embedding") or {}).get("status", "unknown")
    status = (
        "healthy"
        if lightrag_status == "healthy" and local_embedding_status == "healthy"
        else "unhealthy"
    )

    return {
        "status": status,
        "version": "1.0.0",
        "checks": {
            "lightrag": lightrag_status,
            "local_embedding": local_embedding_status,
        },
        "document_audit": audit,
        "startup_reconciliation": getattr(
            app.state,
            "startup_reconciliation",
            {"status": "unknown"},
        ),
    }


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    if path.startswith(("api/", "docs", "redoc", "openapi.json", "assets/")):
        raise HTTPException(status_code=404, detail="Not Found")

    if not _serve_frontend_dist():
        raise HTTPException(status_code=404, detail="Not Found")

    index_path = _frontend_dist_dir() / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return {
        "message": "办公文档智能分类与检索系统后端API",
        "version": "1.0.0",
        "api_prefix": API_PREFIX,
        "docs": "/docs",
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn_options = _build_uvicorn_options()
    logger.info(
        "启动模式：{} host={} port={} workers={}",
        "开发" if uvicorn_options["reload"] else "生产",
        uvicorn_options["host"],
        uvicorn_options["port"],
        uvicorn_options["workers"],
    )

    uvicorn.run("main:app", **uvicorn_options)
