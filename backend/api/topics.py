"""Topics API - 知识图谱和主题端点"""
from fastapi import APIRouter, Query
from typing import Optional, List

from app.core.logger import logger
from app.infra.repositories.entity_repository import EntityRepository
from app.infra.graph_store import GraphStore
from app.services.lightrag_semantic_service import LightRAGSemanticService
from app.services.errors import AppServiceError
from api import success, BusinessException

router = APIRouter()
entity_repo = EntityRepository()
graph_store = GraphStore()
semantic_service = LightRAGSemanticService()


@router.get("/labels", summary="获取 LightRAG 图谱标签列表")
async def get_graph_labels():
    try:
        labels = await semantic_service.list_graph_labels()
        return success(data={"items": labels, "total": len(labels)}, message="获取图谱标签成功")
    except AppServiceError as exc:
        raise BusinessException(exc.code, detail=exc.detail)
    except Exception as e:
        logger.error(f"获取图谱标签失败: {str(e)}")
        raise BusinessException(500, detail=str(e))


@router.get("/graph", summary="获取知识图谱数据")
async def get_knowledge_graph(
    label: Optional[str] = Query(None, description="图谱标签"),
    doc_ids: Optional[List[str]] = Query(None, description="兼容保留字段，目前未生效"),
    max_depth: int = Query(3, ge=1, le=6),
    max_nodes: int = Query(1000, ge=1, le=5000),
):
    """
    获取知识图谱数据（vis-network.js 格式）

    可用于前端可视化展示
    """
    try:
        del doc_ids
        selected_label = str(label or "").strip()
        if not selected_label:
            labels = await semantic_service.list_graph_labels()
            selected_label = labels[0] if labels else ""

        if not selected_label:
            return success(
                data={"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0, "total_docs": 0}, "label": ""},
                message="获取知识图谱成功",
            )

        graph_data = await semantic_service.get_graph(selected_label, max_depth=max_depth, max_nodes=max_nodes)
        return success(data=graph_data, message="获取知识图谱成功")
    except AppServiceError as exc:
        raise BusinessException(exc.code, detail=exc.detail)
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
        if not entity_id or not entity_id.strip():
            raise BusinessException(400, "entity_id 不能为空")

        graph_labels = await semantic_service.list_graph_labels()
        if not graph_labels:
            return success(
                data={"center_entity": entity_id, "direct_relations": [], "related_entities": [entity_id]},
                message="获取相关文档成功",
            )

        graph = await semantic_service.get_graph(graph_labels[0])
        direct_relations = [
            {
                "subject": edge.get("from"),
                "predicate": edge.get("label"),
                "object": edge.get("to"),
                "doc_id": edge.get("doc_id"),
            }
            for edge in graph.get("edges") or []
            if edge.get("from") == entity_id or edge.get("to") == entity_id
        ]
        related_entities = {entity_id}
        for item in direct_relations:
            if item.get("subject"):
                related_entities.add(item["subject"])
            if item.get("object"):
                related_entities.add(item["object"])

        return success(
            data={
                "center_entity": entity_id,
                "direct_relations": direct_relations,
                "related_entities": list(related_entities),
            },
            message="获取相关文档成功",
        )
    except AppServiceError as exc:
        raise BusinessException(exc.code, detail=exc.detail)
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
