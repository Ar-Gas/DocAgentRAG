from fastapi import APIRouter, HTTPException
from utils.classifier import classify_document
from utils.storage import get_document_info, save_classification_result, get_classification_result

router = APIRouter()



@router.post("/trigger/{document_id}")
async def trigger_classification(document_id: str):
    """
    触发文档分类
    """
    try:
        # 获取文档信息
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="文档不存在")

        # 调用分类函数
        classification_result = classify_document(doc_info)

        # 保存分类结果
        save_classification_result(document_id, classification_result)

        return {
            "status": "success",
            "document_id": document_id,
            "classification_result": classification_result,
            "message": "文档分类成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分类失败: {str(e)}")



@router.get("/result/{document_id}")
async def get_classification_result_endpoint(document_id: str):
    """
    获取分类结果
    """
    try:
        result = get_classification_result(document_id)
        if not result:
            raise HTTPException(status_code=404, detail="分类结果不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类结果失败: {str(e)}")
