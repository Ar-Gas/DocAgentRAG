from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from config import API_PREFIX, DATA_DIR, DOC_DIR, CHROMA_DB_PATH, FILE_TYPE_DIRS, DOUBAO_API_KEY, OPENAI_API_KEY
import config as _config
from api import (
    router as api_router,
    BusinessException,
    business_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)
from utils.storage import init_chroma_client, get_chroma_collection, get_all_documents, detect_and_lock_embedding_dim
from utils.logger import setup_logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# 7.1 初始化统一日志
setup_logging()


def check_and_rebuild_chunks():
    """
    检查系统中已有文档的分片完整性，如分片丢失则重新生成
    """
    logger.info("开始检查文档分片完整性...")
    
    try:
        collection = get_chroma_collection()
        if not collection:
            logger.warning("无法获取Chroma集合，跳过分片检查")
            return
        
        # 获取所有JSON中记录的文档
        all_docs = get_all_documents()
        if not all_docs:
            logger.info("系统中没有文档记录")
            return
        
        logger.info(f"系统中共有 {len(all_docs)} 个文档记录")
        
        # 获取Chroma中所有分片的document_id
        chroma_docs = collection.get(include=["metadatas"])
        
        # 统计每个document_id的分片数量
        chroma_doc_counts = {}
        if chroma_docs and chroma_docs.get('metadatas'):
            for metadata in chroma_docs['metadatas']:
                if metadata:
                    doc_id = metadata.get('document_id', '')
                    if doc_id:
                        chroma_doc_counts[doc_id] = chroma_doc_counts.get(doc_id, 0) + 1
        
        # 检查每个文档
        rebuild_count = 0
        missing_docs = []
        
        for doc in all_docs:
            doc_id = doc.get('id')
            filename = doc.get('filename', '未知文件')
            
            if not doc_id:
                continue
            
            # 检查分片是否缺失
            chroma_count = chroma_doc_counts.get(doc_id, 0)
            
            # 简单检查：如果Chroma中没有这个文档的任何分片，认为需要重建
            if chroma_count == 0:
                logger.warning(f"文档 {filename} (ID: {doc_id}) 在向量库中没有分片，需要重新生成")
                missing_docs.append(doc)
                rebuild_count += 1
        
        if missing_docs:
            auto_rebuild = os.getenv("AUTO_REBUILD_CHUNKS_ON_STARTUP", "false").lower() == "true"
            logger.info(f"发现 {len(missing_docs)} 个文档需要重新生成分片")

            if not auto_rebuild:
                logger.info("默认仅检查不自动重建。设置 AUTO_REBUILD_CHUNKS_ON_STARTUP=true 可在启动时重建。")
                logger.info("待重建文档: %s", [doc.get("filename", "未知") for doc in missing_docs[:10]])
                return

            for doc in missing_docs:
                doc_id = doc.get('id')
                filename = doc.get('filename', '未知')
                filepath = doc.get('filepath', '')
                
                if filepath and Path(filepath).exists():
                    logger.info(f"准备重新处理文档: {filename}")
                    try:
                        from utils.storage import save_document_to_chroma
                        success = save_document_to_chroma(filepath, doc_id)
                        if success:
                            logger.info(f"文档重新处理成功: {filename}")
                        else:
                            logger.error(f"文档重新处理失败: {filename}")
                    except Exception as e:
                        logger.error(f"重新处理文档 {filename} 时出错: {str(e)}")
                else:
                    logger.warning(f"文档文件不存在，跳过: {filepath}")
        
        logger.info(f"分片完整性检查完成: 共检查 {len(all_docs)} 个文档, 需要重建 {rebuild_count} 个")
        
    except Exception as e:
        logger.error(f"检查分片完整性时出错: {str(e)}", exc_info=True)

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
    if not DOUBAO_API_KEY and not OPENAI_API_KEY:
        logger.warning("未配置任何 LLM API Key（DOUBAO_API_KEY / OPENAI_API_KEY），"
                       "智能检索将降级为 hybrid 模式，分类功能不可用。")
        _config.LLM_AVAILABLE = False
    else:
        _config.LLM_AVAILABLE = True
        provider = "Doubao" if DOUBAO_API_KEY else "OpenAI-compatible"
        logger.info(f"LLM provider: {provider}")

    logger.info("正在初始化 Chroma 客户端和加载模型...")
    chroma_client, chroma_collection = init_chroma_client()
    if chroma_client and chroma_collection:
        logger.info("Chroma 客户端初始化成功")
    else:
        logger.error("Chroma 客户端初始化失败，请检查模型路径")
    
    # 检查并重建缺失的文档分片
    check_and_rebuild_chunks()

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
    from utils.storage import _chroma_client, _chroma_collection
    chroma_ok = _chroma_client is not None and _chroma_collection is not None
    
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
