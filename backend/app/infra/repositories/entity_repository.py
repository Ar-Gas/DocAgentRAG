"""Entity Repository - 管理文档实体"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database import connect_sqlite
from config import DATA_DIR


class EntityRepository:
    """文档实体数据访问层"""

    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or DATA_DIR)
        self.db_path = Path(db_path or (self.data_dir / "docagent.db"))

    def _connect(self):
        return connect_sqlite(self.db_path)

    def save_entities(self, doc_id: str, entities: List[Dict[str, Any]]) -> bool:
        """
        保存文档实体

        Args:
            doc_id: 文档 ID
            entities: 实体列表 [{"entity_text": "", "entity_type": "", "context": ""}]

        Returns:
            是否成功
        """
        try:
            with self._connect() as conn:
                now = datetime.now().isoformat()
                for entity in entities:
                    entity_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO doc_entities (id, doc_id, entity_text, entity_type, context, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entity_id,
                            doc_id,
                            entity.get("entity_text", ""),
                            entity.get("entity_type", ""),
                            entity.get("context", ""),
                            now
                        )
                    )
                conn.commit()
            return True
        except Exception as e:
            print(f"保存实体失败: {str(e)}")
            return False

    def find_by_text(self, entity_text: str) -> List[Dict[str, Any]]:
        """
        按实体文本查找

        Args:
            entity_text: 实体文本

        Returns:
            包含该实体的所有文档
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT DISTINCT doc_id FROM doc_entities WHERE entity_text = ?
                    """,
                    (entity_text,)
                )
                rows = cursor.fetchall()
                return [{"doc_id": row[0]} for row in rows]
        except Exception:
            return []

    def find_by_doc(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        按文档 ID 查找该文档的所有实体

        Args:
            doc_id: 文档 ID

        Returns:
            该文档的实体列表
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT entity_text, entity_type, context FROM doc_entities
                    WHERE doc_id = ?
                    ORDER BY created_at DESC
                    """,
                    (doc_id,)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "entity_text": row[0],
                        "entity_type": row[1],
                        "context": row[2]
                    }
                    for row in rows
                ]
        except Exception:
            return []

    def delete_by_doc(self, doc_id: str) -> bool:
        """
        删除文档的所有实体

        Args:
            doc_id: 文档 ID

        Returns:
            是否成功
        """
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM doc_entities WHERE doc_id = ?", (doc_id,))
                conn.commit()
            return True
        except Exception:
            return False
