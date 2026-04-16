from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from config import (
    API_PREFIX,
    DATA_DIR,
    DOC_DIR,
    CHROMA_DB_PATH,
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
from app.infra.embedding_provider import detect_and_lock_embedding_dim
from app.infra import vector_store as vector_store_module
from app.infra.vector_store import init_chroma_client
from app.services.indexing_service import IndexingService
from utils.logger import setup_logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# 7.1 初始化统一日志
setup_logging()


def _indexing_service() -> IndexingService:
    return IndexingService()


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


def check_and_rebuild_block_indexes():
    """检查 block 索引就绪状态，必要时触发重建。"""
    logger.info("开始检查 block 索引就绪状态...")

    try:
        service = _indexing_service()
        audit = service.audit_block_index()
        documents = list(audit.get("documents") or [])
        rebuild_candidates = list(audit.get("rebuild_candidates") or [])
        orphan_block_ids = list(audit.get("orphan_block_ids") or [])
        candidate_set = set(rebuild_candidates)

        if orphan_block_ids:
            logger.warning("检测到 %s 个孤儿 block，建议执行 scripts/backfill_block_index.py 清理。", len(orphan_block_ids))

        if not rebuild_candidates:
            logger.info("block 索引检查完成: 共检查 %s 个文档，未发现需重建文档", len(documents))
            return audit

        auto_rebuild = _env_flag("AUTO_REBUILD_BLOCK_INDEX_ON_STARTUP")
        logger.info("发现 %s 个文档 block 索引未就绪", len(rebuild_candidates))

        if not auto_rebuild:
            logger.info("默认仅检查不自动重建。设置 AUTO_REBUILD_BLOCK_INDEX_ON_STARTUP=true 可在启动时重建。")
            logger.info(
                "待重建文档: %s",
                [
                    item.get("filename") or item.get("document_id") or "未知"
                    for item in documents
                    if item.get("document_id") in candidate_set
                ][:10],
            )
            return audit

        for item in documents:
            document_id = item.get("document_id")
            if document_id not in candidate_set:
                continue
            try:
                result = service.index_document(document_id, force=True)
                if (result or {}).get("block_index_status") == "ready":
                    logger.info(
                        "block 索引重建成功: %s (%s)",
                        document_id,
                        ", ".join(item.get("rebuild_reasons") or []) or "manual",
                    )
                else:
                    logger.error(
                        "block 索引重建失败: %s - %s",
                        document_id,
                        (result or {}).get("error", "unknown error"),
                    )
            except Exception as exc:
                logger.error("重建 block 索引失败: %s - %s", document_id, exc)

        logger.info("block 索引检查完成: 共检查 %s 个文档, 需要重建 %s 个", len(documents), len(rebuild_candidates))
        return audit
    except Exception as exc:
        logger.error("检查 block 索引时出错: %s", exc, exc_info=True)
        return {"documents": [], "rebuild_candidates": [], "orphan_block_ids": []}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("办公文档智能分类与检索系统启动中...")
    logger.info("=" * 50)
    
    for dir_path in [DOC_DIR, DATA_DIR, CHROMA_DB_PATH]:
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

    logger.info("正在初始化 Chroma 客户端和加载模型...")
    chroma_client, chroma_collection = init_chroma_client()
    if chroma_client and chroma_collection:
        logger.info("Chroma 客户端初始化成功")
    else:
        logger.error("Chroma 客户端初始化失败，请检查模型路径")
    
    # 检查并重建缺失的 block 索引
    check_and_rebuild_block_indexes()

    # 4.1 检查并锁定 embedding 维度（Doubao/BGE 切换后的一致性保障）
    detect_and_lock_embedding_dim()
    
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
_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    chroma_ok = (
        vector_store_module._chroma_client is not None
        and vector_store_module._chroma_collection is not None
    )
    
    status = "healthy" if chroma_ok else "unhealthy"
    
    return {
        "status": status,
        "version": "1.0.0",
        "checks": {
            "chroma": "ok" if chroma_ok else "failed"
        }
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
