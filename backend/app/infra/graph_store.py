"""Graph store - 知识图谱持久化存储"""
import json
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.database import connect_sqlite
from config import DATA_DIR


class GraphStore:
    """知识图谱持久化存储，基于 SQLite"""

    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or DATA_DIR)
        self.db_path = Path(db_path or (self.data_dir / "docagent.db"))

    def _connect(self):
        return connect_sqlite(self.db_path)

    def save_graph(self, graph_data: Dict[str, Any]) -> bool:
        """
        保存图数据为 JSON（可选，用于导出）

        Args:
            graph_data: 图数据

        Returns:
            是否成功
        """
        try:
            graph_path = self.data_dir / "graph_export.json"
            with open(graph_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存图数据失败: {str(e)}")
            return False

    def load_graph(self) -> Optional[Dict[str, Any]]:
        """
        从 JSON 加载图数据

        Returns:
            图数据或 None
        """
        try:
            graph_path = self.data_dir / "graph_export.json"
            if not graph_path.exists():
                return None

            with open(graph_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_triples(self, doc_ids: Optional[list] = None) -> list:
        """
        从数据库获取三元组

        Args:
            doc_ids: 文档 ID 列表，None 表示全部

        Returns:
            三元组列表
        """
        try:
            with self._connect() as conn:
                if doc_ids is None:
                    cursor = conn.execute(
                        """
                        SELECT subject, predicate, object, doc_id, confidence
                        FROM kg_triples
                        ORDER BY confidence DESC
                        """
                    )
                else:
                    placeholders = ",".join("?" * len(doc_ids))
                    cursor = conn.execute(
                        f"""
                        SELECT subject, predicate, object, doc_id, confidence
                        FROM kg_triples
                        WHERE doc_id IN ({placeholders})
                        ORDER BY confidence DESC
                        """,
                        doc_ids
                    )

                rows = cursor.fetchall()
                return [
                    {
                        "subject": row[0],
                        "predicate": row[1],
                        "object": row[2],
                        "doc_id": row[3],
                        "confidence": row[4]
                    }
                    for row in rows
                ]
        except Exception:
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """获取图统计信息"""
        try:
            with self._connect() as conn:
                # 总三元组数
                cursor = conn.execute("SELECT COUNT(*) FROM kg_triples")
                total_triples = cursor.fetchone()[0]

                # 不同实体数
                cursor = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT subject AS entity FROM kg_triples
                        UNION
                        SELECT object AS entity FROM kg_triples
                    )
                    """
                )
                total_entities = cursor.fetchone()[0]

                # 最常见的谓语
                cursor = conn.execute(
                    """
                    SELECT predicate, COUNT(*) as count
                    FROM kg_triples
                    GROUP BY predicate
                    ORDER BY count DESC
                    LIMIT 10
                    """
                )
                top_predicates = [{"predicate": row[0], "count": row[1]} for row in cursor.fetchall()]

                return {
                    "total_triples": total_triples,
                    "total_entities": total_entities,
                    "top_predicates": top_predicates
                }
        except Exception:
            return {"total_triples": 0, "total_entities": 0, "top_predicates": []}
