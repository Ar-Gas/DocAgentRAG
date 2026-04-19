from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
import os

from config import (
    API_PREFIX,
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
from app.services.document_audit_service import DocumentAuditService
setup_logging()


def _document_audit_service() -> DocumentAuditService:
    return DocumentAuditService()


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


def _load_cors_settings() -> tuple[list[str], bool]:
    origins_env = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
    if not origins:
        origins = ["*"]
    allow_credentials = "*" not in origins
    return origins, allow_credentials


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

    audit = await refresh_document_audit_state(register_local_only=True)
    app.state.document_audit = audit
    logger.info(
        "document audit: sqlite=%s local_files=%s legacy_json=%s untracked=%s pending=%s lightrag=%s registered_local_only=%s",
        audit.get("sqlite_documents", 0),
        audit.get("local_files", 0),
        audit.get("legacy_json_documents", 0),
        len(audit.get("untracked_local_files", [])),
        audit.get("pending_ingest_documents", 0),
        (audit.get("lightrag") or {}).get("status", "unknown"),
        audit.get("registered_local_only_documents", 0),
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

# 2.2 兼容旧 /api 路径，307 临时重定向到 /api/v1（未来版本删除）
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def legacy_api_redirect(path: str, request: Request):
    # 防止 /api/v1/... 被误捕获后产生重定向循环
    if path.startswith("v1"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    new_url = str(request.url).replace("/api/", "/api/v1/", 1)
    return RedirectResponse(url=new_url, status_code=307)


@app.get("/", summary="根路径")
async def root():
    return {
        "message": "办公文档智能分类与检索系统后端API",
        "version": "1.0.0",
        "api_prefix": API_PREFIX,
        "docs": "/docs"
    }

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
    }

if __name__ == "__main__":
    import uvicorn
    
    dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"
    
    logger.info(f"启动模式：{'开发' if dev_mode else '生产'}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=6008,
        reload=dev_mode,
        workers=1 if dev_mode else 4
    )
