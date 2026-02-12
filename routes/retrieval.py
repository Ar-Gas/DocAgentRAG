from fastapi import APIRouter, HTTPException, Query
from utils.retriever import search_documents

router = APIRouter()

@router.get("/search")
async def search(query: str = Query(..., description="搜索关键词"), limit: int = Query(10, description="返回结果数量限制")):
    """
    搜索文档
    """
    try:
        import time
        start_time = time.time()
        
        # 调用搜索函数
        results = search_documents(query, limit)
        
        # 计算搜索耗时
        search_time = time.time() - start_time
        
        return {
            "status": "success",
            "query": query,
            "results": results,
            "search_time": round(search_time, 4),
            "total_results": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")
