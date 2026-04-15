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
from app.core.document_governance import normalize_document_governance
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
                    """
                    CREATE TABLE IF NOT EXISTS roles (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        builtin INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        primary_department_id TEXT,
                        role_code TEXT NOT NULL,
                        last_login_at TEXT,
                        external_identity_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS departments (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        parent_id TEXT,
                        manager_user_id TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_department_memberships (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        department_id TEXT NOT NULL,
                        membership_type TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS business_categories (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        scope_type TEXT NOT NULL,
                        department_id TEXT,
                        status TEXT NOT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_by TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_shared_departments (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        department_id TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS auth_sessions (
                        token TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id TEXT PRIMARY KEY,
                        user_id TEXT,
                        username_snapshot TEXT,
                        department_id TEXT,
                        role_code TEXT,
                        action_type TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        result TEXT NOT NULL,
                        ip_address TEXT,
                        metadata_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
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
                for _col_sql in [
                    "ALTER TABLE documents ADD COLUMN visibility_scope TEXT DEFAULT 'department'",
                    "ALTER TABLE documents ADD COLUMN owner_department_id TEXT",
                    "ALTER TABLE documents ADD COLUMN business_category_id TEXT",
                    "ALTER TABLE documents ADD COLUMN role_restriction TEXT",
                    "ALTER TABLE documents ADD COLUMN confidentiality_level TEXT DEFAULT 'internal'",
                    "ALTER TABLE documents ADD COLUMN document_status TEXT DEFAULT 'draft'",
                    "ALTER TABLE documents ADD COLUMN is_public_restricted INTEGER DEFAULT 0",
                ]:
                    try:
                        connection.execute(_col_sql)
                    except Exception:
                        pass
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
        payload = self._apply_enterprise_document_defaults(dict(doc_info))
        return {
            "id": payload["id"],
            "filename": payload.get("filename", ""),
            "filepath": payload.get("filepath", ""),
            "file_type": payload.get("file_type", ""),
            "classification_result": payload.get("classification_result"),
            "created_at": payload.get("created_at"),
            "created_at_iso": payload.get("created_at_iso"),
            "updated_at": payload.get("updated_at"),
            "visibility_scope": payload.get("visibility_scope", "department"),
            "owner_department_id": payload.get("owner_department_id"),
            "business_category_id": payload.get("business_category_id"),
            "role_restriction": payload.get("role_restriction"),
            "confidentiality_level": payload.get("confidentiality_level", "internal"),
            "document_status": payload.get("document_status", "draft"),
            "is_public_restricted": payload.get("is_public_restricted", 0),
            "payload": json.dumps(payload, ensure_ascii=False),
        }

    def _apply_enterprise_document_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_document_governance(payload, current_user=None)

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
                    created_at, created_at_iso, updated_at,
                    visibility_scope, owner_department_id, business_category_id,
                    role_restriction, confidentiality_level, document_status,
                    is_public_restricted, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename,
                    filepath = excluded.filepath,
                    file_type = excluded.file_type,
                    classification_result = excluded.classification_result,
                    created_at = excluded.created_at,
                    created_at_iso = excluded.created_at_iso,
                    updated_at = excluded.updated_at,
                    visibility_scope = excluded.visibility_scope,
                    owner_department_id = excluded.owner_department_id,
                    business_category_id = excluded.business_category_id,
                    role_restriction = excluded.role_restriction,
                    confidentiality_level = excluded.confidentiality_level,
                    document_status = excluded.document_status,
                    is_public_restricted = excluded.is_public_restricted,
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
                    payload["visibility_scope"],
                    payload["owner_department_id"],
                    payload["business_category_id"],
                    payload["role_restriction"],
                    payload["confidentiality_level"],
                    payload["document_status"],
                    payload["is_public_restricted"],
                    payload["payload"],
                ),
            )
            connection.commit()

        if mirror:
            self._write_document_json(json.loads(payload["payload"]))
        return True

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()

        if not row:
            return None
        return self._apply_enterprise_document_defaults(json.loads(row["payload"]))

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
        return [self._apply_enterprise_document_defaults(json.loads(row["payload"])) for row in rows]

    def delete_document(self, document_id: str, mirror: bool = True) -> bool:
        with self._connect() as connection:
            connection.execute("DELETE FROM document_shared_departments WHERE document_id = ?", (document_id,))
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
        return [self._apply_enterprise_document_defaults(json.loads(row["payload"])) for row in rows]

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

    def _ensure_builtin_roles(self) -> None:
        builtin_roles = [
            ("system_admin", "系统管理员", "平台级治理、配置与审计管理", 1),
            ("department_admin", "部门管理员", "部门内文档治理与成员管理", 1),
            ("employee", "普通员工", "文档上传、检索与协作访问", 1),
            ("audit_readonly", "审计只读", "审计日志与合规信息只读访问", 1),
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO roles (code, name, description, builtin)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    builtin = excluded.builtin
                """,
                builtin_roles,
            )
            connection.commit()

    def list_roles(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT code, name, description, builtin FROM roles ORDER BY builtin DESC, code ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def ensure_enterprise_defaults(self, admin_password_hash: str) -> Dict[str, Any]:
        self._ensure_builtin_roles()
        pending_department_id = self.upsert_department(
            {"id": "dept-pending", "name": "待归属", "status": "enabled", "parent_id": None}
        )
        self.upsert_business_category(
            {
                "id": "cat-pending",
                "name": "待整理",
                "scope_type": "system",
                "department_id": None,
                "status": "enabled",
                "sort_order": 999,
                "created_by": "system",
            }
        )
        if not self.get_user_by_username("admin"):
            self.upsert_user(
                {
                    "id": "user-admin",
                    "username": "admin",
                    "password_hash": admin_password_hash,
                    "display_name": "系统管理员",
                    "status": "enabled",
                    "primary_department_id": pending_department_id,
                    "role_code": "system_admin",
                }
            )
        return {"admin_username": "admin", "pending_department_id": pending_department_id}

    def upsert_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        existing = self.get_user_by_username(payload["username"])
        user_id = existing["id"] if existing else payload.get("id") or f"user-{uuid.uuid4().hex}"
        created_at = payload.get("created_at") or (existing["created_at"] if existing else now)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, username, password_hash, display_name, status,
                    primary_department_id, role_code, last_login_at,
                    external_identity_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username = excluded.username,
                    password_hash = excluded.password_hash,
                    display_name = excluded.display_name,
                    status = excluded.status,
                    primary_department_id = excluded.primary_department_id,
                    role_code = excluded.role_code,
                    last_login_at = excluded.last_login_at,
                    external_identity_id = excluded.external_identity_id,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    payload["username"],
                    payload["password_hash"],
                    payload["display_name"],
                    payload.get("status", "enabled"),
                    payload.get("primary_department_id"),
                    payload["role_code"],
                    payload.get("last_login_at"),
                    payload.get("external_identity_id"),
                    created_at,
                    now,
                ),
            )
            connection.commit()
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def touch_user_last_login(self, user_id: str, last_login_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                (last_login_at, last_login_at, user_id),
            )
            connection.commit()

    def upsert_department(self, payload: Dict[str, Any]) -> str:
        department_id = payload.get("id") or f"dept-{uuid.uuid4().hex}"
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO departments (
                    id, name, parent_id, manager_user_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    parent_id = excluded.parent_id,
                    manager_user_id = excluded.manager_user_id,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    department_id,
                    payload["name"],
                    payload.get("parent_id"),
                    payload.get("manager_user_id"),
                    payload.get("status", "enabled"),
                    payload.get("created_at", now),
                    now,
                ),
            )
            connection.commit()
        return department_id

    def list_departments(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, parent_id, manager_user_id, status, created_at, updated_at
                FROM departments
                ORDER BY name ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_user_department_memberships(
        self,
        user_id: str,
        primary_department_id: str,
        collaborative_department_ids: List[str],
    ) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM user_department_memberships WHERE user_id = ?", (user_id,))
            connection.execute(
                """
                INSERT INTO user_department_memberships (id, user_id, department_id, membership_type)
                VALUES (?, ?, ?, ?)
                """,
                (f"{user_id}:primary", user_id, primary_department_id, "primary"),
            )
            for department_id in dict.fromkeys(collaborative_department_ids):
                connection.execute(
                    """
                    INSERT INTO user_department_memberships (id, user_id, department_id, membership_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (f"{user_id}:{department_id}", user_id, department_id, "collaborative"),
                )
            connection.commit()

    def list_user_department_memberships(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT department_id, membership_type
                FROM user_department_memberships
                WHERE user_id = ?
                ORDER BY rowid ASC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_managed_department_ids(self, user_id: str) -> List[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM departments
                WHERE manager_user_id = ? AND status = 'enabled'
                ORDER BY rowid ASC
                """,
                (user_id,),
            ).fetchall()
        return [row["id"] for row in rows]

    def upsert_business_category(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        category_id = payload.get("id") or f"cat-{uuid.uuid4().hex}"
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO business_categories (
                    id, name, scope_type, department_id, status, sort_order,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    scope_type = excluded.scope_type,
                    department_id = excluded.department_id,
                    status = excluded.status,
                    sort_order = excluded.sort_order,
                    created_by = excluded.created_by,
                    updated_at = excluded.updated_at
                """,
                (
                    category_id,
                    payload["name"],
                    payload["scope_type"],
                    payload.get("department_id"),
                    payload.get("status", "enabled"),
                    payload.get("sort_order", 0),
                    payload["created_by"],
                    payload.get("created_at", now),
                    now,
                ),
            )
            connection.commit()
        return {
            "id": category_id,
            "name": payload["name"],
            "scope_type": payload["scope_type"],
            "department_id": payload.get("department_id"),
            "status": payload.get("status", "enabled"),
            "sort_order": payload.get("sort_order", 0),
        }

    def list_business_categories(
        self,
        scope_type: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT id, name, scope_type, department_id, status, sort_order, created_by, created_at, updated_at
            FROM business_categories
            WHERE 1 = 1
        """
        params: List[Any] = []
        if scope_type:
            sql += " AND scope_type = ?"
            params.append(scope_type)
        if department_id is not None:
            sql += " AND department_id = ?"
            params.append(department_id)
        sql += " ORDER BY sort_order ASC, name ASC"

        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def replace_document_shared_departments(self, document_id: str, department_ids: List[str]) -> None:
        unique_ids = [department_id for department_id in dict.fromkeys(department_ids) if department_id]
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM document_shared_departments WHERE document_id = ?",
                (document_id,),
            )
            for department_id in unique_ids:
                connection.execute(
                    """
                    INSERT INTO document_shared_departments (id, document_id, department_id)
                    VALUES (?, ?, ?)
                    """,
                    (f"{document_id}:{department_id}", document_id, department_id),
                )
            connection.commit()

    def list_document_shared_departments(self, document_id: str) -> List[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT department_id
                FROM document_shared_departments
                WHERE document_id = ?
                ORDER BY rowid ASC
                """,
                (document_id,),
            ).fetchall()
        return [row["department_id"] for row in rows]

    def create_auth_session(self, user_id: str, token: str, expires_at: str) -> str:
        now = datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO auth_sessions (
                    token, user_id, expires_at, created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (token, user_id, expires_at, now, now),
            )
            connection.commit()
        return token

    def get_auth_session(self, token: str) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM auth_sessions WHERE token = ?",
                (token,),
            ).fetchone()
        return dict(row) if row else None

    def delete_auth_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            connection.commit()

    def delete_auth_sessions_by_user(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            connection.commit()

    def insert_audit_log(self, payload: Dict[str, Any]) -> str:
        audit_id = payload.get("id") or f"audit-{uuid.uuid4().hex}"
        created_at = payload.get("created_at") or datetime.now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (
                    id, user_id, username_snapshot, department_id, role_code,
                    action_type, target_type, target_id, result, ip_address,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    payload.get("user_id"),
                    payload.get("username_snapshot"),
                    payload.get("department_id"),
                    payload.get("role_code"),
                    payload["action_type"],
                    payload["target_type"],
                    payload["target_id"],
                    payload["result"],
                    payload.get("ip_address"),
                    json.dumps(payload.get("metadata_json") or {}, ensure_ascii=False),
                    created_at,
                ),
            )
            connection.commit()
        return audit_id

    def list_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                **dict(row),
                "metadata_json": json.loads(row["metadata_json"] or "{}"),
            }
            for row in rows
        ]


_metadata_stores: Dict[str, DocumentMetadataStore] = {}


def get_metadata_store(data_dir: Optional[Path] = None, db_path: Optional[Path] = None) -> DocumentMetadataStore:
    effective_data_dir = Path(data_dir or DATA_DIR)
    effective_db_path = Path(db_path or (effective_data_dir / "docagent.db"))
    cache_key = f"{effective_data_dir}:{effective_db_path}"
    if cache_key not in _metadata_stores:
        _metadata_stores[cache_key] = DocumentMetadataStore(db_path=effective_db_path, data_dir=effective_data_dir)
    return _metadata_stores[cache_key]
