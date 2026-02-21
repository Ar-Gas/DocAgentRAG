from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import logging
import os

from config import API_PREFIX, DATA_DIR, DOC_DIR, CHROMA_DB_PATH, FILE_TYPE_DIRS
from api import (
    router as api_router,
    BusinessException,
    business_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)
from utils.storage import init_chroma_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    
    logger.info("正在初始化 Chroma 客户端和加载模型...")
    chroma_client = init_chroma_client()
    if chroma_client:
        logger.info("Chroma 客户端初始化成功")
    else:
        logger.error("Chroma 客户端初始化失败，请检查模型路径")
    
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=API_PREFIX)

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
    from utils.storage import _chroma_client
    chroma_ok = _chroma_client is not None
    
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
