from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime
import os
import shutil
from utils.document_processor import process_document
from utils.storage import save_document_info, get_document_info

router = APIRouter()

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    上传文档
    """
    try:
        # 生成文件名（原文件名+时间戳）
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{os.path.splitext(file.filename)[0]}_{timestamp}{os.path.splitext(file.filename)[1]}"
        filepath = os.path.join("doc", filename)
        
        # 保存文件
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 提取文档信息
        doc_info = {
            "id": filename,
            "filename": file.filename,
            "path": filepath,
            "upload_time": datetime.now().isoformat(),
            "file_type": os.path.splitext(file.filename)[1].lower()
        }
        
        # 处理文档内容
        content = process_document(filepath)
        doc_info["content"] = content
        
        # 保存文档信息到JSON
        save_document_info(doc_info)
        
        return {
            "status": "success",
            "document_id": filename,
            "filepath": filepath,
            "message": "文档上传成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档上传失败: {str(e)}")

@router.get("/info/{document_id}")
async def get_document(document_id: str):
    """
    获取文档信息
    """
    try:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="文档不存在")
        return doc_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取文档信息失败: {str(e)}")
