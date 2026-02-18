from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

# 导入你的模块
from api import router as api_router
from utils.storage import (
    init_chroma_client,
    DOC_DIR,
    DATA_DIR,
    CHROMA_DB_PATH
)

# ===================== 优化1：统一配置日志 =====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== 优化2：启动时的生命周期管理 =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup 事件：应用启动时执行
    logger.info("=" * 50)
    logger.info("办公文档智能分类与检索系统启动中...")
    logger.info("=" * 50)
    
    # 1. 确保必要目录存在
    for dir_path in [DOC_DIR, DATA_DIR, CHROMA_DB_PATH]:
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"确保目录存在：{dir_path}")
    
    # 2. 初始化 Chroma 客户端（加载模型+连接数据库）
    logger.info("正在初始化 Chroma 客户端和加载模型...")
    chroma_client = init_chroma_client()
    if chroma_client:
        logger.info("✅ Chroma 客户端初始化成功")
    else:
        logger.error("❌ Chroma 客户端初始化失败，请检查模型路径")
    
    logger.info("=" * 50)
    logger.info("系统启动完成！")
    logger.info("=" * 50)
    
    yield  # 应用运行中
    
    # Shutdown 事件：应用关闭时执行（可选）
    logger.info("系统正在关闭...")

# ===================== 创建 FastAPI 应用 =====================
app = FastAPI(
    title="办公文档智能分类与检索系统",
    description="支持文档上传、智能分类、向量检索、扫描版PDF OCR等功能",
    version="1.0.0",
    lifespan=lifespan  # 绑定生命周期管理
)

# ===================== 配置 CORS =====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ 生产环境请改成具体的前端域名，比如 ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== 集成 API 路由 =====================
app.include_router(api_router, prefix="/api", tags=["文档管理"])

# ===================== 根路径 =====================
@app.get("/", summary="根路径", description="返回系统欢迎信息")
async def root():
    return {
        "message": "办公文档智能分类与检索系统后端API",
        "version": "1.0.0",
        "docs": "/docs"  # 提示可以访问 Swagger 文档
    }

# ===================== 优化3：完善的健康检查 =====================
@app.get("/health", summary="健康检查", description="检查系统状态，包括Chroma连接")
async def health_check():
    # 检查 Chroma 客户端是否初始化成功
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

# ===================== 启动应用 =====================
if __name__ == "__main__":
    import uvicorn
    
    # 优化4：区分开发和生产环境
    # 可以通过环境变量控制，比如 DEV_MODE=1
    dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"
    
    logger.info(f"启动模式：{'开发' if dev_mode else '生产'}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=6008,
        reload=dev_mode,  # 开发环境开启 reload，生产环境关闭
        workers=1 if dev_mode else 4  # 生产环境可以多 worker
    )