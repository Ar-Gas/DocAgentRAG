"""Graph index - 知识图谱索引"""
import json
from typing import List, Dict, Any, Optional
from app.infra.repositories.kg_repository import KGRepository


class GraphIndex:
    """知识图谱索引，使用 NetworkX 存储和查询"""

    def __init__(self):
        self.kg_repo = KGRepository()
        self._graph_cache = None

    def build_graph(self, doc_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        构建知识图谱，返回 vis-network.js 格式

        Args:
            doc_ids: 文档 ID 列表，None 表示全部

        Returns:
            包含 nodes 和 edges 的图数据
        """
        triples = self.kg_repo.get_triples(doc_ids)

        # 构建节点和边
        nodes_dict = {}
        edges = []

        for triple in triples:
            subject = triple.get("subject", "")
            predicate = triple.get("predicate", "")
            obj = triple.get("object", "")
            doc_id = triple.get("doc_id", "")

            # 添加节点
            if subject not in nodes_dict:
                nodes_dict[subject] = {
                    "id": subject,
                    "label": subject,
                    "title": subject,
                    "type": "entity"
                }

            if obj not in nodes_dict:
                nodes_dict[obj] = {
                    "id": obj,
                    "label": obj,
                    "title": obj,
                    "type": "entity"
                }

            # 添加边
            edge_id = f"{subject}_{predicate}_{obj}"
            edges.append({
                "id": edge_id,
                "from": subject,
                "to": obj,
                "label": predicate,
                "title": f"{subject} {predicate} {obj}",
                "doc_id": doc_id,
                "arrows": "to"
            })

        # 转换为 vis.js 格式
        nodes = list(nodes_dict.values())

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_docs": len(set([e.get("doc_id") for e in edges if e.get("doc_id")]))
            }
        }

    def query_related_entities(self, entity: str, depth: int = 2) -> Dict[str, Any]:
        """
        查询与实体相关的其他实体和关系

        Args:
            entity: 中心实体
            depth: 关系深度（1/2/3）

        Returns:
            相关实体和关系
        """
        # 第一层：直接相关的三元组
        direct_triples = self.kg_repo.find_by_entity(entity)

        result = {
            "center_entity": entity,
            "direct_relations": [],
            "related_entities": set([entity])
        }

        for triple in direct_triples:
            subject = triple.get("subject")
            obj = triple.get("object")
            predicate = triple.get("predicate")

            result["direct_relations"].append({
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "doc_id": triple.get("doc_id")
            })

            # 记录相关实体
            if subject != entity:
                result["related_entities"].add(subject)
            if obj != entity:
                result["related_entities"].add(obj)

        return {
            "center_entity": entity,
            "direct_relations": result["direct_relations"],
            "related_entities": list(result["related_entities"])
        }

    def get_node_info(self, node_id: str) -> Dict[str, Any]:
        """获取节点的详细信息"""
        triples = self.kg_repo.find_by_entity(node_id)

        incoming = [t for t in triples if t.get("object") == node_id]
        outgoing = [t for t in triples if t.get("subject") == node_id]

        return {
            "node_id": node_id,
            "incoming_relations": [
                {
                    "from": t.get("subject"),
                    "predicate": t.get("predicate"),
                    "doc_id": t.get("doc_id")
                }
                for t in incoming
            ],
            "outgoing_relations": [
                {
                    "to": t.get("object"),
                    "predicate": t.get("predicate"),
                    "doc_id": t.get("doc_id")
                }
                for t in outgoing
            ]
        }
