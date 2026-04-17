"""QA Session Repository - 管理问答历史"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database import connect_sqlite
from config import DATA_DIR


class QASessionRepository:
    """问答会话数据访问层"""

    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or DATA_DIR)
        self.db_path = Path(db_path or (self.data_dir / "docagent.db"))

    def _connect(self):
        return connect_sqlite(self.db_path)

    def save(
        self,
        query: str,
        doc_ids: List[str],
        answer: str,
        citations: List[Dict[str, Any]],
        session_id: Optional[str] = None,
    ) -> str:
        """
        保存一个问答会话

        Args:
            query: 用户查询
            doc_ids: 参与问答的文档 ID 列表
            answer: LLM 生成的答案
            citations: 引用列表 [{"doc_id": "", "block_id": "", "excerpt": ""}]

        Returns:
            会话 ID
        """
        import json

        try:
            session_id = session_id or str(uuid.uuid4())
            now = datetime.now().isoformat()

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO qa_sessions (id, query, doc_ids, answer, citations, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        query,
                        json.dumps(doc_ids, ensure_ascii=False),
                        answer,
                        json.dumps(citations, ensure_ascii=False),
                        now
                    )
                )
                conn.commit()
            return session_id
        except Exception as e:
            print(f"保存问答会话失败: {str(e)}")
            return ""

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取一个问答会话

        Args:
            session_id: 会话 ID

        Returns:
            会话数据或 None
        """
        import json

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, query, doc_ids, answer, citations, created_at
                    FROM qa_sessions WHERE id = ?
                    """,
                    (session_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return None

                return {
                    "id": row[0],
                    "query": row[1],
                    "doc_ids": json.loads(row[2]),
                    "answer": row[3],
                    "citations": json.loads(row[4]),
                    "created_at": row[5]
                }
        except Exception:
            return None

    def list_by_doc(self, doc_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取某个文档相关的所有问答会话

        Args:
            doc_id: 文档 ID
            limit: 限制数量

        Returns:
            问答会话列表
        """
        import json

        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, query, answer, created_at
                    FROM qa_sessions
                    WHERE doc_ids LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (f'%"{doc_id}"%', limit)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "query": row[1],
                        "answer": row[2],
                        "created_at": row[3]
                    }
                    for row in rows
                ]
        except Exception:
            return []

    def list_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, query, answer, created_at
                    FROM qa_sessions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "query": row[1],
                        "answer": row[2],
                        "created_at": row[3],
                    }
                    for row in rows
                ]
        except Exception:
            return []
