import json
import hashlib
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.database import connect_sqlite
from config import DATA_DIR

logger = logging.getLogger(__name__)


class DocumentMetadataStore:
    """SQLite-backed metadata store with JSON mirroring for backward compatibility."""

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
                # 6.1 documents 表状态机字段（幂等 ALTER，已有列会被忽略）
                for _col_sql in [
                    "ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'ready'",
                    "ALTER TABLE documents ADD COLUMN error_message TEXT",
                    "ALTER TABLE documents ADD COLUMN retry_count INTEGER DEFAULT 0",
                ]:
                    try:
                        connection.execute(_col_sql)
                    except Exception:
                        pass  # 列已存在时忽略
                connection.commit()

            self._sync_from_json_files()
            self._initialized = True

    def _sync_from_json_files(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for json_path in sorted(self.data_dir.glob("*.json")):
            if json_path.name == "classification_tree.json":
                try:
                    with open(json_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                    self.save_artifact("classification_tree", payload, mirror=False)
                except Exception as exc:
                    logger.warning("同步分类树 JSON 失败: %s", exc)
                continue

            try:
                with open(json_path, "r", encoding="utf-8") as handle:
                    doc_info = json.load(handle)
                if doc_info.get("id") and doc_info.get("filename"):
                    self.upsert_document(doc_info, mirror=False)
            except Exception as exc:
                logger.warning("同步元数据 JSON 失败 %s: %s", json_path.name, exc)

    def _serialize_doc(self, doc_info: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(doc_info)
        return {
            "id": payload["id"],
            "filename": payload.get("filename", ""),
            "filepath": payload.get("filepath", ""),
            "file_type": payload.get("file_type", ""),
            "classification_result": payload.get("classification_result"),
            "created_at": payload.get("created_at"),
            "created_at_iso": payload.get("created_at_iso"),
            "updated_at": payload.get("updated_at"),
            "payload": json.dumps(payload, ensure_ascii=False),
        }

    def _write_document_json(self, doc_info: Dict[str, Any]) -> None:
        output_path = self.data_dir / f"{doc_info['id']}.json"
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(doc_info, handle, ensure_ascii=False, indent=2)

    def _delete_document_json(self, document_id: str) -> None:
        output_path = self.data_dir / f"{document_id}.json"
        if output_path.exists():
            output_path.unlink()

    def _write_artifact_json(self, name: str, payload: Dict[str, Any]) -> None:
        output_name = "classification_tree.json" if name == "classification_tree" else f"{name}.json"
        output_path = self.data_dir / output_name
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def upsert_document(self, doc_info: Dict[str, Any], mirror: bool = False) -> bool:
        if not isinstance(doc_info, dict) or not doc_info.get("id"):
            return False

        payload = self._serialize_doc(doc_info)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO documents (
                    id, filename, filepath, file_type, classification_result,
                    created_at, created_at_iso, updated_at, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename,
                    filepath = excluded.filepath,
                    file_type = excluded.file_type,
                    classification_result = excluded.classification_result,
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
                    payload["created_at"],
                    payload["created_at_iso"],
                    payload["updated_at"],
                    payload["payload"],
                ),
            )
            connection.commit()

        if mirror:
            self._write_document_json(doc_info)
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

    def delete_document(self, document_id: str, mirror: bool = True) -> bool:
        with self._connect() as connection:
            connection.execute("DELETE FROM document_contents WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_segments WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM document_artifacts WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            connection.commit()
        if mirror:
            self._delete_document_json(document_id)
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

    def save_artifact(self, name: str, payload: Dict[str, Any], mirror: bool = False) -> bool:
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

        if mirror:
            self._write_artifact_json(name, payload)
        return True

    def load_artifact(self, name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM artifacts WHERE name = ?",
                (name,),
            ).fetchone()
        if row:
            return json.loads(row["payload"])

        json_name = "classification_tree.json" if name == "classification_tree" else f"{name}.json"
        json_path = self.data_dir / json_name
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                self.save_artifact(name, payload, mirror=False)
                return payload
            except Exception as exc:
                logger.warning("加载 JSON artifact 失败 %s: %s", name, exc)
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
