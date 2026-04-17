"""KG Repository - 管理知识图谱三元组"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database import connect_sqlite
from config import DATA_DIR


class KGRepository:
    """知识图谱数据访问层"""

    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or DATA_DIR)
        self.db_path = Path(db_path or (self.data_dir / "docagent.db"))

    def _connect(self):
        return connect_sqlite(self.db_path)

    def save_triples(self, doc_id: str, triples: List[Dict[str, Any]]) -> bool:
        """
        保存知识图谱三元组

        Args:
            doc_id: 文档 ID
            triples: 三元组列表 [{"subject": "", "predicate": "", "object": ""}]

        Returns:
            是否成功
        """
        try:
            with self._connect() as conn:
                now = datetime.now().isoformat()
                for triple in triples:
                    triple_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO kg_triples (id, doc_id, subject, predicate, object, confidence, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            triple_id,
                            doc_id,
                            triple.get("subject", ""),
                            triple.get("predicate", ""),
                            triple.get("object", ""),
                            triple.get("confidence", 1.0),
                            now
                        )
                    )
                conn.commit()
            return True
        except Exception as e:
            print(f"保存知识图谱失败: {str(e)}")
            return False

    def get_triples(self, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        获取三元组

        Args:
            doc_ids: 文档 ID 列表，None 表示获取所有

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

    def find_by_entity(self, entity: str) -> List[Dict[str, Any]]:
        """
        查找包含该实体的所有三元组（作为主语或宾语）

        Args:
            entity: 实体文本

        Returns:
            三元组列表
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT subject, predicate, object, doc_id
                    FROM kg_triples
                    WHERE subject = ? OR object = ?
                    ORDER BY confidence DESC
                    """,
                    (entity, entity)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "subject": row[0],
                        "predicate": row[1],
                        "object": row[2],
                        "doc_id": row[3]
                    }
                    for row in rows
                ]
        except Exception:
            return []

    def delete_by_doc(self, doc_id: str) -> bool:
        """
        删除文档的所有三元组

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM kg_triples WHERE doc_id = ?", (doc_id,))
                conn.commit()
            return True
        except Exception:
            return False
