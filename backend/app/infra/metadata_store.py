import json
import hashlib
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logger import logger
from app.core.database import connect_sqlite
from config import DATA_DIR


class DocumentMetadataStore:
    """SQLite-backed metadata store."""

    def __init__(self, db_path: Optional[Path] = None, data_dir: Optional[Path] = None):
        self.data_dir = Path(data_dir or DATA_DIR)
        self.db_path = Path(db_path or (self.data_dir / "docagent.db"))
        self._lock = threading.Lock()
        self._initialized = False
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    def _initialize(self) -> None:
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        filepath TEXT,
                        file_type TEXT,
                        classification_result TEXT,
                        classification_id TEXT,
                        classification_path TEXT,
                        classification_score REAL,
                        classification_source TEXT,
                        classification_candidates TEXT,
                        created_at REAL,
                        created_at_iso TEXT,
                        updated_at TEXT,
                        payload TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifacts (
                        name TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_contents (
                        document_id TEXT PRIMARY KEY,
                        full_content TEXT NOT NULL,
                        preview_content TEXT,
                        content_hash TEXT,
                        extraction_status TEXT NOT NULL,
                        parser_name TEXT,
                        extraction_error TEXT,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_segments (
                        segment_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        segment_index INTEGER NOT NULL,
                        segment_type TEXT,
                        title TEXT,
                        content TEXT NOT NULL,
                        page_number INTEGER,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_artifacts (
                        artifact_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        artifact_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS classification_tables (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        title TEXT,
                        summary TEXT,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_document_segments_document_id ON document_segments(document_id, segment_index)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_document_artifacts_document_id ON document_artifacts(document_id, artifact_type)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_classification_tables_updated_at ON classification_tables(updated_at)"
                )

                # ====== PHASE 1 新增：RAG 相关表 ======
                # doc_entities：存储文档中抽取的实体
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS doc_entities (
                        id TEXT PRIMARY KEY,
                        doc_id TEXT NOT NULL,
                        entity_text TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        context TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # qa_sessions：存储问答历史和引用溯源
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS qa_sessions (
                        id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        doc_ids TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        citations TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # kg_triples：知识图谱三元组（主语、关系、宾语）
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kg_triples (
                        id TEXT PRIMARY KEY,
                        doc_id TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        predicate TEXT NOT NULL,
                        object TEXT NOT NULL,
                        confidence REAL DEFAULT 1.0,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # classification_feedback：分类反馈，支持 few-shot 学习
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS classification_feedback (
                        id TEXT PRIMARY KEY,
                        doc_id TEXT NOT NULL,
                        original_label TEXT,
                        corrected_label TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                # 创建索引以提高查询性能
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_doc_entities_doc ON doc_entities(doc_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_doc_entities_text ON doc_entities(entity_text)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_qa_sessions_created ON qa_sessions(created_at)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kg_triples_doc ON kg_triples(doc_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kg_triples_subject ON kg_triples(subject)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kg_triples_object ON kg_triples(object)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_classification_feedback_doc ON classification_feedback(doc_id)"
                )
                # ====== PHASE 1 新增：END ======
                # 6.1 documents 表状态机字段（幂等 ALTER，已有列会被忽略）
                for _col_sql in [
                    "ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'ready'",
                    "ALTER TABLE documents ADD COLUMN error_message TEXT",
                    "ALTER TABLE documents ADD COLUMN retry_count INTEGER DEFAULT 0",
                    "ALTER TABLE documents ADD COLUMN classification_id TEXT",
                    "ALTER TABLE documents ADD COLUMN classification_path TEXT",
                    "ALTER TABLE documents ADD COLUMN classification_score REAL",
                    "ALTER TABLE documents ADD COLUMN classification_source TEXT",
                    "ALTER TABLE documents ADD COLUMN classification_candidates TEXT",
                ]:
                    try:
                        connection.execute(_col_sql)
                    except Exception:
                        pass  # 列已存在时忽略
                connection.commit()

            self._initialized = True

    def _serialize_doc(self, doc_info: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(doc_info)
        return {
            "id": payload["id"],
            "filename": payload.get("filename", ""),
            "filepath": payload.get("filepath", ""),
            "file_type": payload.get("file_type", ""),
            "classification_result": payload.get("classification_result"),
            "classification_id": payload.get("classification_id"),
            "classification_path": payload.get("classification_path"),
            "classification_score": payload.get("classification_score"),
            "classification_source": payload.get("classification_source"),
            "classification_candidates": payload.get("classification_candidates"),
            "created_at": payload.get("created_at"),
            "created_at_iso": payload.get("created_at_iso"),
            "updated_at": payload.get("updated_at"),
            "payload": json.dumps(payload, ensure_ascii=False),
        }

    def upsert_document(self, doc_info: Dict[str, Any]) -> bool:
        if not isinstance(doc_info, dict) or not doc_info.get("id"):
            return False

        payload = self._serialize_doc(doc_info)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, filename, filepath, file_type, classification_result,
                    classification_id, classification_path, classification_score, classification_source,
                    classification_candidates,
                    created_at, created_at_iso, updated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename,
                    filepath = excluded.filepath,
                    file_type = excluded.file_type,
                    classification_result = excluded.classification_result,
                    classification_id = excluded.classification_id,
                    classification_path = excluded.classification_path,
                    classification_score = excluded.classification_score,
                    classification_source = excluded.classification_source,
                    classification_candidates = excluded.classification_candidates,
                    created_at = excluded.created_at,
                    created_at_iso = excluded.created_at_iso,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    payload["id"],
                    payload["filename"],
                    payload["filepath"],
                    payload["file_type"],
                    payload["classification_result"],
                    payload["classification_id"],
                    payload["classification_path"],
                    payload["classification_score"],
                    payload["classification_source"],
                    payload["classification_candidates"],
                    payload["created_at"],
                    payload["created_at_iso"],
                    payload["updated_at"],
                    payload["payload"],
                ),
            )
            connection.commit()
        return True

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()

        if not row:
            return None
        return json.loads(row["payload"])

    def list_documents(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM documents
                ORDER BY
                    COALESCE(updated_at, created_at_iso, '') DESC,
                    COALESCE(created_at, 0) DESC
                """
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as connection:
            connection.execute("DELETE FROM document_contents WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_segments WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_artifacts WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            connection.commit()
        return True

    def update_document(self, document_id: str, updated_fields: Dict[str, Any]) -> bool:
        current = self.get_document(document_id)
        if current is None:
            return False

        merged = dict(current)
        merged.update(updated_fields)
        if "updated_at" not in merged:
            merged["updated_at"] = datetime.now().isoformat()
        return self.upsert_document(merged)

    def list_by_classification(self, classification: str) -> List[Dict[str, Any]]:
        if not classification:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM documents WHERE classification_result = ? ORDER BY COALESCE(updated_at, created_at_iso, '') DESC",
                (classification,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def save_classification_result(self, document_id: str, classification_result: str) -> bool:
        current = self.get_document(document_id)
        if current is None:
            return False

        current["classification_result"] = classification_result
        current["classification_time"] = datetime.now().isoformat()
        current["updated_at"] = datetime.now().isoformat()
        return self.upsert_document(current)

    def update_document_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """6.1 更新文档处理状态（pending / processing / ready / failed）"""
        now = datetime.now().isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE documents
                    SET status = ?,
                        error_message = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (status, error_message, now, document_id),
                )
                if status == "failed":
                    connection.execute(
                        "UPDATE documents SET retry_count = retry_count + 1 WHERE id = ?",
                        (document_id,),
                    )
                connection.commit()
            return True
        except Exception as exc:
            logger.error(f"update_document_status 失败: {exc}")
            return False

    def save_artifact(self, name: str, payload: Dict[str, Any]) -> bool:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (name, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (name, json.dumps(payload, ensure_ascii=False), now),
            )
            connection.commit()
        return True

    def load_artifact(self, name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM artifacts WHERE name = ?",
                (name,),
            ).fetchone()
        if row:
            return json.loads(row["payload"])
        return None

    def save_document_content(
        self,
        document_id: str,
        *,
        full_content: str,
        preview_content: Optional[str] = None,
        extraction_status: str = "ready",
        parser_name: Optional[str] = None,
        extraction_error: Optional[str] = None,
    ) -> bool:
        if not document_id or self.get_document(document_id) is None:
            return False

        now = datetime.now().isoformat()
        preview = preview_content if preview_content is not None else full_content[:1000]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_contents (
                    document_id, full_content, preview_content, content_hash,
                    extraction_status, parser_name, extraction_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    full_content = excluded.full_content,
                    preview_content = excluded.preview_content,
                    content_hash = excluded.content_hash,
                    extraction_status = excluded.extraction_status,
                    parser_name = excluded.parser_name,
                    extraction_error = excluded.extraction_error,
                    updated_at = excluded.updated_at
                """,
                (
                    document_id,
                    full_content,
                    preview,
                    hashlib.md5(full_content.encode("utf-8")).hexdigest(),
                    extraction_status,
                    parser_name,
                    extraction_error,
                    now,
                ),
            )
            connection.commit()

        current = self.get_document(document_id) or {}
        current.update(
            {
                "preview_content": preview,
                "full_content_length": len(full_content),
                "extraction_status": extraction_status,
                "parser_name": parser_name,
                "extraction_error": extraction_error,
                "updated_at": now,
            }
        )
        return self.upsert_document(current)

    def get_document_content(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    document_id,
                    full_content,
                    preview_content,
                    content_hash,
                    extraction_status,
                    parser_name,
                    extraction_error,
                    updated_at
                FROM document_contents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def replace_document_segments(self, document_id: str, segments: List[Dict[str, Any]]) -> bool:
        if self.get_document(document_id) is None:
            return False

        now = datetime.now().isoformat()
        normalized_segments = []
        for index, segment in enumerate(segments):
            segment_id = segment.get("segment_id") or f"{document_id}#{index}"
            normalized_segments.append(
                (
                    segment_id,
                    document_id,
                    segment.get("segment_index", index),
                    segment.get("segment_type", "chunk"),
                    segment.get("title"),
                    segment.get("content", ""),
                    segment.get("page_number"),
                    json.dumps(segment.get("metadata", {}), ensure_ascii=False),
                    now,
                )
            )

        with self._connect() as connection:
            connection.execute("DELETE FROM document_segments WHERE document_id = ?", (document_id,))
            if normalized_segments:
                connection.executemany(
                    """
                    INSERT INTO document_segments (
                        segment_id, document_id, segment_index, segment_type,
                        title, content, page_number, payload, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    normalized_segments,
                )
            connection.commit()
        return True

    def list_document_segments(self, document_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    segment_id,
                    document_id,
                    segment_index,
                    segment_type,
                    title,
                    content,
                    page_number,
                    payload,
                    updated_at
                FROM document_segments
                WHERE document_id = ?
                ORDER BY segment_index ASC
                """,
                (document_id,),
            ).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("payload") or "{}")
            results.append(item)
        return results

    def save_document_artifact(
        self,
        document_id: str,
        artifact_type: str,
        payload: Dict[str, Any],
        artifact_id: Optional[str] = None,
    ) -> Optional[str]:
        if self.get_document(document_id) is None or not artifact_type:
            return None

        artifact_id = artifact_id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO document_artifacts (artifact_id, document_id, artifact_type, payload, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    document_id = excluded.document_id,
                    artifact_type = excluded.artifact_type,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (artifact_id, document_id, artifact_type, json.dumps(payload, ensure_ascii=False), now),
            )
            connection.commit()
        return artifact_id

    def upsert_document_artifact(
        self,
        document_id: str,
        artifact_type: str,
        payload: Dict[str, Any],
    ) -> Optional[str]:
        if not document_id or not artifact_type:
            return None
        artifact_id = f"{document_id}:{artifact_type}"
        return self.save_document_artifact(
            document_id=document_id,
            artifact_type=artifact_type,
            payload=payload,
            artifact_id=artifact_id,
        )

    def list_document_artifacts(self, document_id: str, artifact_type: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT artifact_id, document_id, artifact_type, payload, updated_at
            FROM document_artifacts
            WHERE document_id = ?
        """
        params: List[Any] = [document_id]
        if artifact_type:
            query += " AND artifact_type = ?"
            params.append(artifact_type)
        query += " ORDER BY updated_at DESC"

        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()

        results: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            results.append(item)
        return results

    def get_document_artifact(
        self,
        document_id: str,
        artifact_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Return only the deterministic {document_id}:{artifact_type} artifact.

        Returns None when that deterministic row does not exist. Any legacy or
        caller-specific fallback must be handled outside this helper.
        """
        artifact_id = f"{document_id}:{artifact_type}"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_id, document_id, artifact_type, payload, updated_at
                FROM document_artifacts
                WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()

        if not row:
            return None

        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

    def save_classification_table(self, table_payload: Dict[str, Any], table_id: Optional[str] = None) -> str:
        table_id = table_id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        created_at = table_payload.get("created_at", now)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO classification_tables (id, query, title, summary, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    query = excluded.query,
                    title = excluded.title,
                    summary = excluded.summary,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    table_id,
                    table_payload.get("query", ""),
                    table_payload.get("title"),
                    table_payload.get("summary"),
                    json.dumps({**table_payload, "id": table_id, "created_at": created_at}, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )
            connection.commit()
        return table_id

    def get_classification_table(self, table_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM classification_tables WHERE id = ?",
                (table_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_classification_tables(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM classification_tables
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]


_metadata_stores: Dict[str, DocumentMetadataStore] = {}


def get_metadata_store(data_dir: Optional[Path] = None, db_path: Optional[Path] = None) -> DocumentMetadataStore:
    effective_data_dir = Path(data_dir or DATA_DIR)
    effective_db_path = Path(db_path or (effective_data_dir / "docagent.db"))
    cache_key = f"{effective_data_dir}:{effective_db_path}"
    if cache_key not in _metadata_stores:
        _metadata_stores[cache_key] = DocumentMetadataStore(db_path=effective_db_path, data_dir=effective_data_dir)
    return _metadata_stores[cache_key]
