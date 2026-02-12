from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
import os

app = FastAPI(
    title="办公文档智能分类与检索系统",
    description="支持文档上传、智能分类、向量检索等功能",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 文档模型
class Document(BaseModel):
    id: str
    title: str
    type: str
    content: Optional[str] = None
    created_at: str

# 模拟文档数据
documents = [
    {
        "id": "1",
        "title": "项目计划文档",
        "type": "计划",
        "content": "这是一个项目计划文档",
        "created_at": "2024-01-01"
    },
    {
        "id": "2",
        "title": "技术方案文档",
        "type": "技术",
        "content": "这是一个技术方案文档",
        "created_at": "2024-01-02"
    }
]

@app.get("/api/documents", response_model=List[Document])
async def get_documents():
    return documents

@app.get("/api/documents/{doc_id}", response_model=Document)
async def get_document(doc_id: str):
    for doc in documents:
        if doc["id"] == doc_id:
            return doc
    raise HTTPException(status_code=404, detail="文档不存在")

@app.post("/api/upload", response_model=dict)
async def upload_document(file: UploadFile = File(...)):
    try:
        file_path = f"/tmp/{file.filename}"
        with open(file_path, "wb") as f:
            f.write(await file.read())
        return {
            "message": "文档上传成功",
            "filename": file.filename,
            "document_id": f"doc_{len(documents) + 1}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

@app.post("/api/search", response_model=List[Document])
async def search_documents(query: str):
    results = []
    for doc in documents:
        if query in doc["title"] or (doc["content"] and query in doc["content"]):
            results.append(doc)
    return results

@app.get("/")
async def root():
    return {"message": "办公文档智能分类与检索系统后端API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_new:app", host="0.0.0.0", port=6010, reload=True)

