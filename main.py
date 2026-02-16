from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
import socket
from routes import document, classification, retrieval

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="DocAgentRAG API",
    description="文档智能处理与检索增强生成系统",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应设置具体的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建必要的目录
os.makedirs("doc", exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs("models", exist_ok=True)



# 健康检查接口
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(document.router, prefix="/api/document", tags=["document"])
app.include_router(classification.router, prefix="/api/classification", tags=["classification"])
app.include_router(retrieval.router, prefix="/api/retrieval", tags=["retrieval"])

if __name__ == "__main__":
    # 获取局域网IP
    def get_local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip

    local_ip = get_local_ip()
    logger.info(f"Starting server on http://{local_ip}:8000")
    logger.info(f"API documentation available at http://{local_ip}:8000/docs")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
