"""Topics API - 知识图谱和主题端点"""
from fastapi import APIRouter, Query
from typing import Optional, List

from app.core.logger import logger
from app.domain.indexing.graph_index import GraphIndex
from app.infra.repositories.entity_repository import EntityRepository
from app.infra.graph_store import GraphStore
from api import success, BusinessException

router = APIRouter()
graph_index = GraphIndex()
entity_repo = EntityRepository()
graph_store = GraphStore()


@router.get("/graph", summary="获取知识图谱数据")
async def get_knowledge_graph(
    doc_ids: Optional[List[str]] = Query(None, description="限定的文档 ID")
):
    """
    获取知识图谱数据（vis-network.js 格式）

    可用于前端可视化展示
    """
    try:
        graph_data = graph_index.build_graph(doc_ids)
        return success(data=graph_data, message="获取知识图谱成功")

    except Exception as e:
        logger.error(f"获取知识图谱失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/entities", summary="搜索实体")
async def search_entities(
    text: str = Query(..., description="实体文本搜索"),
    limit: int = Query(10, ge=1, le=100)
):
    """
    按实体文本搜索，返回包含该实体的所有文档
    """
    try:
        if not text or not text.strip():
            raise BusinessException(400, "搜索文本不能为空")

        # 查找包含该实体的文档
        docs = entity_repo.find_by_text(text)

        return success(
            data={"entity": text, "documents": docs[:limit]},
            message="搜索实体成功"
        )

    except BusinessException:
        raise
    except Exception as e:
        logger.error(f"实体搜索失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/{entity_id}/related", summary="获取相关文档")
async def get_related_documents(entity_id: str):
    """
    获取与某个实体相关的所有文档和关系
    """
    try:
        related = graph_index.query_related_entities(entity_id)
        return success(data=related, message="获取相关文档成功")

    except Exception as e:
        logger.error(f"获取相关文档失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/stats", summary="获取图谱统计")
async def get_graph_statistics():
    """获取知识图谱的统计信息"""
    try:
        stats = graph_store.get_statistics()
        return success(data=stats, message="获取统计成功")

    except Exception as e:
        logger.error(f"获取统计失败: {str(e)}")
        raise BusinessException(500, detail=str(e))
