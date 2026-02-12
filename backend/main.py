from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import router as api_router

app = FastAPI(
    title="办公文档智能分类与检索系统",
    description="支持文档上传、智能分类、向量检索等功能",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 集成API路由
app.include_router(api_router, prefix="/api", tags=["文档管理"])

@app.get("/")
async def root():
    return {"message": "办公文档智能分类与检索系统后端API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=6008, reload=True)
