"""Graph retrieval - 基于知识图谱的检索"""
from typing import List, Dict, Any, Optional
from app.infra.repositories.kg_repository import KGRepository


class GraphRetrieval:
    """基于知识图谱的实体关系检索"""

    def __init__(self):
        self.kg_repo = KGRepository()

    async def search_by_entity(self, entity: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        按实体查询相关文档

        Args:
            entity: 实体文本
            top_k: 返回前 k 个结果

        Returns:
            包含该实体的文档列表
        """
        # 查找所有包含该实体的三元组
        triples = self.kg_repo.find_by_entity(entity)

        # 提取文档 ID 并去重
        doc_ids = list(set([t["doc_id"] for t in triples]))

        # 构造结果
        results = [
            {
                "doc_id": doc_id,
                "entity": entity,
                "related_triples": [t for t in triples if t["doc_id"] == doc_id]
            }
            for doc_id in doc_ids[:top_k]
        ]

        return results

    async def search_by_relationship(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        按关系查询

        Args:
            subject: 主语（可选）
            predicate: 谓语（可选）
            obj: 宾语（可选）
            top_k: 返回前 k 个结果

        Returns:
            匹配的三元组和相关文档
        """
        # 获取所有三元组
        all_triples = self.kg_repo.get_triples()

        # 过滤
        filtered = []
        for triple in all_triples:
            if subject and triple["subject"] != subject:
                continue
            if predicate and triple["predicate"] != predicate:
                continue
            if obj and triple["object"] != obj:
                continue
            filtered.append(triple)

        return filtered[:top_k]
