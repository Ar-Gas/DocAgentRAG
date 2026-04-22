import os
import re
import shutil
import asyncio
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.core.logger import logger
from app.infra.lightrag_client import LightRAGClient
from app.infra.metadata_store import INGEST_FIELD_UNSET
from app.infra.file_utils import enrich_document_file_state as _enrich_document_file_state
from app.infra.repositories.document_artifact_repository import DocumentArtifactRepository
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.infra.vector_store import get_block_collection
from app.services.document_vector_index_service import DocumentVectorIndexService
from app.services.document_stage_aggregator import aggregate_runtime_view
from app.services.errors import AppServiceError
from app.services.extraction_service import ExtractionService
from app.services.indexing_service import IndexingService
from app.services.local_embedding_runtime import LocalEmbeddingRuntime
from app.services.rag_runtime_guard import RagCircuitBreaker, build_document_profile
from config import ALLOWED_EXTENSIONS, BASE_DIR, DATA_DIR, DOC_DIR, EXTENSION_TO_DIR, MAX_FILE_SIZE
from utils.retriever import get_query_parser
from utils.search_cache import get_search_cache

LIGHTRAG_SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".mdx", ".pdf", ".docx", ".pptx", ".xlsx", ".rtf",
    ".odt", ".tex", ".epub", ".html", ".htm", ".csv", ".json", ".xml",
    ".yaml", ".yml", ".log", ".conf", ".ini", ".properties", ".sql",
    ".bat", ".sh", ".c", ".h", ".cpp", ".hpp", ".py", ".java", ".js",
    ".ts", ".swift", ".go", ".rb", ".php", ".css", ".scss", ".less",
}
LIGHTRAG_UNSUPPORTED_ERROR_MARKER = "unsupported file type"
LIGHTRAG_LOCAL_ONLY_FAILURE_MARKERS = (
    "file content contains only whitespace",
    "[file extraction]file contains only whitespace",
    "no content could be extracted",
)
LIGHTRAG_STALE_PENDING_THRESHOLD = timedelta(minutes=15)
LIGHTRAG_STALE_PROCESSING_THRESHOLD = timedelta(minutes=30)


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _content_repository() -> DocumentContentRepository:
    return DocumentContentRepository(data_dir=DATA_DIR)


def _segment_repository() -> DocumentSegmentRepository:
    return DocumentSegmentRepository(data_dir=DATA_DIR)


def _artifact_repository() -> DocumentArtifactRepository:
    return DocumentArtifactRepository(data_dir=DATA_DIR)


def _vector_index_service() -> DocumentVectorIndexService:
    return DocumentVectorIndexService(
        document_repository=_document_repository(),
        content_repository=_content_repository(),
        segment_repository=_segment_repository(),
    )


def get_document_info(document_id: str):
    return _document_repository().get(document_id)


def get_all_documents():
    return _document_repository().list_all()


def update_document_info(document_id: str, updated_info: Dict) -> bool:
    return _document_repository().update(document_id, updated_info)


def update_document_ingest_status(
    document_id: str,
    ingest_status: str,
    ingest_error: Optional[str] = None,
    lightrag_track_id: Optional[str] | object = INGEST_FIELD_UNSET,
    lightrag_doc_id: Optional[str] | object = INGEST_FIELD_UNSET,
    last_status_sync_at: Optional[str] = None,
) -> bool:
    return _document_repository().update_ingest_status(
        document_id,
        ingest_status=ingest_status,
        ingest_error=ingest_error,
        lightrag_track_id=lightrag_track_id,
        lightrag_doc_id=lightrag_doc_id,
        last_status_sync_at=last_status_sync_at,
    )


def save_classification_result(document_id: str, classification_result: str) -> bool:
    return _document_repository().save_classification_result(document_id, classification_result)


def get_document_content_record(document_id: str):
    return _content_repository().get(document_id)


def list_document_segments(document_id: str):
    return _segment_repository().list(document_id)


def list_document_artifacts(document_id: str, artifact_type: Optional[str] = None):
    return _artifact_repository().list(document_id, artifact_type)


def get_document_artifact(document_id: str, artifact_type: str):
    return _artifact_repository().get(document_id, artifact_type)


def enrich_document_file_state(doc_info: Optional[Dict], persist: bool = True) -> Dict:
    return _enrich_document_file_state(
        doc_info,
        base_dir=BASE_DIR,
        doc_dir=DOC_DIR,
        get_document_info=get_document_info,
        update_document_info=update_document_info,
        persist=persist,
    )


def save_document_summary_for_classification(
    filepath,
    full_content: Optional[str] = None,
    parser_name: Optional[str] = None,
    display_filename: Optional[str] = None,
):
    return _vector_index_service().save_document_summary_for_classification(
        filepath,
        full_content=full_content,
        parser_name=parser_name,
        display_filename=display_filename,
    )


def delete_document(document_id: str) -> bool:
    _delete_document_blocks(document_id)
    return _document_repository().delete(document_id)


def _delete_document_blocks(document_id: str) -> None:
    collection = get_block_collection()
    if collection is None or not document_id:
        return

    try:
        results = collection.get(where={"document_id": document_id})
        ids = list((results or {}).get("ids") or [])
        if ids:
            collection.delete(ids=ids)
    except Exception as exc:
        logger.warning("删除文档 block 失败: {}", exc)


def _count_blocks(document_id: str) -> int:
    collection = get_block_collection()
    if collection is not None:
        try:
            results = collection.get(where={"document_id": document_id})
            return len((results or {}).get("ids") or [])
        except Exception as exc:
            logger.warning("统计 block 数量失败: {}", exc)

    artifact = get_document_artifact(document_id, "reader_blocks") or {}
    return len(((artifact.get("payload") or {}).get("blocks")) or [])


def get_block_status(document_id: str) -> Dict:
    doc_info = get_document_info(document_id)
    if not doc_info:
        return {
            "document_id": document_id,
            "exists": False,
            "has_blocks": False,
            "block_count": 0,
            "block_index_status": None,
            "chunk_count": 0,
            "has_chunks": False,
            "chunk_info": None,
            "in_sync": False,
        }

    block_count = _count_blocks(document_id)
    expected_block_count = doc_info.get("block_count")
    in_sync = expected_block_count is None or expected_block_count == block_count
    status = doc_info.get("block_index_status")

    return {
        "document_id": document_id,
        "exists": True,
        "has_blocks": block_count > 0,
        "block_count": block_count,
        "expected_block_count": expected_block_count,
        "block_index_status": status,
        "index_version": doc_info.get("index_version"),
        "indexed_content_hash": doc_info.get("indexed_content_hash"),
        "last_indexed_at": doc_info.get("last_indexed_at"),
        "block_index_error": doc_info.get("block_index_error"),
        "chunk_count": block_count,
        "has_chunks": block_count > 0,
        "chunk_info": None,
        "in_sync": in_sync,
    }


class DocumentService:
    def __init__(
        self,
        *,
        document_repository: Optional[DocumentRepository] = None,
        content_repository: Optional[DocumentContentRepository] = None,
        segment_repository: Optional[DocumentSegmentRepository] = None,
        artifact_repository: Optional[DocumentArtifactRepository] = None,
        data_dir: Path = DATA_DIR,
        doc_dir: Path = DOC_DIR,
        lightrag_client=None,
        local_embedding_runtime=None,
        extraction_service=None,
        indexing_service=None,
        enqueue_background: bool = True,
    ):
        self.document_repository = document_repository
        self.content_repository = content_repository
        self.segment_repository = segment_repository
        self.artifact_repository = artifact_repository
        self.data_dir = Path(data_dir)
        self.doc_dir = Path(doc_dir)
        self.lightrag_client = lightrag_client or LightRAGClient()
        self.local_embedding_runtime = local_embedding_runtime or LocalEmbeddingRuntime()
        self.enqueue_background = enqueue_background
        self.extraction_service = extraction_service or ExtractionService()
        self.indexing_service = indexing_service or IndexingService()
        self.rag_circuit_breaker = RagCircuitBreaker()
        self._batch_import_task = None
        self._batch_import_status = self._initial_batch_import_status()

    def recover_stale_lightrag_queue(self) -> Dict:
        try:
            health = self._run_coroutine(self.lightrag_client.health()) or {}
        except Exception as exc:
            return {
                "status": "failed",
                "triggered": False,
                "pending_documents": 0,
                "reason": str(exc),
            }

        pipeline_busy = bool(health.get("busy") or health.get("pipeline_busy"))
        pending_documents = [
            item
            for item in (self._document_repository().list_all() or [])
            if (
                isinstance(item, dict)
                and str(item.get("ingest_status") or "").lower() in {"queued", "processing"}
                and str(item.get("lightrag_track_id") or "").strip()
            )
        ]
        if pipeline_busy or not pending_documents:
            return {
                "status": "skipped",
                "triggered": False,
                "pending_documents": len(pending_documents),
                "pipeline_busy": pipeline_busy,
            }

        try:
            payload = self._run_coroutine(self.lightrag_client.reprocess_failed_documents()) or {}
        except Exception as exc:
            return {
                "status": "failed",
                "triggered": False,
                "pending_documents": len(pending_documents),
                "reason": str(exc),
            }

        now = datetime.now().isoformat()
        for item in pending_documents:
            self._update_ingest_status(
                item["id"],
                ingest_status=str(item.get("ingest_status") or "queued").lower() or "queued",
                ingest_error=item.get("ingest_error"),
                lightrag_track_id=item.get("lightrag_track_id"),
                lightrag_doc_id=item.get("lightrag_doc_id"),
                last_status_sync_at=now,
            )

        return {
            "status": "triggered",
            "triggered": True,
            "pending_documents": len(pending_documents),
            "response": payload,
        }

    @staticmethod
    def _supports_lightrag_ingest(file_type: str) -> bool:
        return str(file_type or "").strip().lower() in LIGHTRAG_SUPPORTED_EXTENSIONS

    def _document_repository(self) -> DocumentRepository:
        return self.document_repository or _document_repository()

    def _mark_stage(self, document_id: str, stage_name: str, **kwargs) -> None:
        self._document_repository().upsert_stage(document_id, stage_name, **kwargs)

    def _load_stage_map(self, document_id: str) -> Dict[str, Dict]:
        return {
            row["stage_name"]: row
            for row in self._document_repository().list_stages(document_id)
        }

    def _sync_aggregate_status_fields(self, document_id: str) -> Dict[str, object]:
        stage_map = self._load_stage_map(document_id)
        aggregated = aggregate_runtime_view(stage_map)
        self._document_repository().update(
            document_id,
            {
                "ingest_status": aggregated["ingest_status"],
                "ingest_error": aggregated["ingest_error"],
                "local_index_status": aggregated["local_index_status"],
                "local_index_error": aggregated["local_index_error"],
            },
        )
        return aggregated

    def _repository_db_path(self) -> Optional[Path]:
        store = getattr(self._document_repository(), "_store", None)
        db_path = getattr(store, "db_path", None)
        return Path(db_path) if db_path else None

    def _content_repository(self) -> DocumentContentRepository:
        return self.content_repository or DocumentContentRepository(
            db_path=self._repository_db_path(),
            data_dir=self.data_dir,
        )

    def _segment_repository(self) -> DocumentSegmentRepository:
        return self.segment_repository or DocumentSegmentRepository(
            db_path=self._repository_db_path(),
            data_dir=self.data_dir,
        )

    def _artifact_repository(self) -> DocumentArtifactRepository:
        return self.artifact_repository or DocumentArtifactRepository(
            db_path=self._repository_db_path(),
            data_dir=self.data_dir,
        )

    def _get_document_info(self, document_id: str):
        if self.document_repository is None:
            return get_document_info(document_id)
        return self.document_repository.get(document_id)

    def _update_document_info(self, document_id: str, updated_info: Dict) -> bool:
        if self.document_repository is None:
            return update_document_info(document_id, updated_info)
        return self.document_repository.update(document_id, updated_info)

    def _update_ingest_status(
        self,
        document_id: str,
        *,
        ingest_status: str,
        ingest_error: Optional[str] = None,
        lightrag_track_id: Optional[str] | object = INGEST_FIELD_UNSET,
        lightrag_doc_id: Optional[str] | object = INGEST_FIELD_UNSET,
        last_status_sync_at: Optional[str] = None,
    ) -> bool:
        if self.document_repository is None:
            return update_document_ingest_status(
                document_id,
                ingest_status,
                ingest_error=ingest_error,
                lightrag_track_id=lightrag_track_id,
                lightrag_doc_id=lightrag_doc_id,
                last_status_sync_at=last_status_sync_at,
            )
        return self.document_repository.update_ingest_status(
            document_id,
            ingest_status=ingest_status,
            ingest_error=ingest_error,
            lightrag_track_id=lightrag_track_id,
            lightrag_doc_id=lightrag_doc_id,
            last_status_sync_at=last_status_sync_at,
        )

    def _hydrate_document(self, doc_info: Dict) -> Dict:
        hydrated = _enrich_document_file_state(
            doc_info,
            base_dir=BASE_DIR,
            doc_dir=self.doc_dir,
            get_document_info=self._get_document_info,
            update_document_info=self._update_document_info,
            persist=True,
        )
        normalized = self._normalize_document_status_fields(hydrated)
        if isinstance(normalized, dict) and normalized.get("id"):
            normalized["processing_stages"] = self._load_stage_map(normalized["id"])
        return normalized

    def _normalize_document_status_fields(self, doc_info: Dict) -> Dict:
        if not isinstance(doc_info, dict) or not doc_info.get("id"):
            return doc_info

        content_record = self._content_repository().get(doc_info["id"]) or {}
        has_content = bool(
            str(content_record.get("full_content") or "").strip()
            or str(content_record.get("preview_content") or "").strip()
            or str(doc_info.get("preview_content") or "").strip()
        )
        extraction_status = str(
            content_record.get("extraction_status")
            or doc_info.get("extraction_status")
            or ""
        ).lower()
        updates: Dict[str, object] = {}

        if not str(doc_info.get("ingest_status") or "").strip():
            updates["ingest_status"] = "local_only"
        if self._is_lightrag_unsupported_failure(
            doc_info.get("file_type", ""),
            doc_info.get("ingest_error", ""),
        ):
            updates["ingest_status"] = "local_only"
            updates["ingest_error"] = None
            updates["lightrag_track_id"] = None
            updates["lightrag_doc_id"] = None
        if has_content and extraction_status == "ready":
            if str(doc_info.get("local_index_status") or "").lower() in {"", "queued", "processing"}:
                updates["local_index_status"] = "ready"
            if not str(doc_info.get("preview_content") or "").strip() and content_record.get("preview_content"):
                updates["preview_content"] = content_record.get("preview_content")
            if not doc_info.get("full_content_length") and content_record.get("full_content"):
                updates["full_content_length"] = len(str(content_record.get("full_content") or ""))
            if not doc_info.get("parser_name") and content_record.get("parser_name"):
                updates["parser_name"] = content_record.get("parser_name")
            if doc_info.get("local_index_error") == "Embedding dimension 1024 does not match collection dimensionality 384":
                updates["local_index_error"] = None

        if not updates:
            return doc_info

        updates["updated_at"] = datetime.now().isoformat()
        self._update_document_info(doc_info["id"], updates)
        normalized = dict(doc_info)
        normalized.update(updates)
        return normalized

    @staticmethod
    def _run_coroutine(coro):
        result_holder = {}
        error_holder = {}

        def runner() -> None:
            try:
                result_holder["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover - defensive bridge
                error_holder["error"] = exc

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        import threading

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if error_holder:
            raise error_holder["error"]
        return result_holder.get("value")

    @staticmethod
    def _normalize_lightrag_doc_status(value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized.startswith("docstatus."):
            normalized = normalized.split(".", 1)[1]
        return normalized

    @staticmethod
    def _parse_iso_datetime(value: object) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @classmethod
    def _extract_remote_processing_start(cls, remote_doc: Dict) -> Optional[datetime]:
        metadata = remote_doc.get("metadata")
        if isinstance(metadata, dict):
            processing_start_time = metadata.get("processing_start_time")
            if processing_start_time is not None:
                try:
                    return datetime.fromtimestamp(
                        float(processing_start_time),
                        tz=timezone.utc,
                    )
                except (TypeError, ValueError, OSError):
                    pass
        return None

    @classmethod
    def _extract_last_sync_time(cls, doc_info: Dict) -> Optional[datetime]:
        return cls._parse_iso_datetime(doc_info.get("last_status_sync_at"))

    @classmethod
    def _is_stale_remote_status(
        cls,
        doc_info: Dict,
        remote_doc: Dict,
        normalized_statuses: set[str],
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        if not normalized_statuses:
            return False

        reference_now = now or datetime.now(timezone.utc)
        started_at = cls._extract_remote_processing_start(remote_doc)
        last_sync_at = cls._extract_last_sync_time(doc_info)
        if started_at is not None and last_sync_at is not None:
            started_at = max(started_at, last_sync_at)
        elif started_at is None:
            started_at = last_sync_at
        if started_at is None:
            return False

        age = reference_now - started_at
        if age.total_seconds() < 0:
            return False

        if normalized_statuses <= {"pending"}:
            return age >= LIGHTRAG_STALE_PENDING_THRESHOLD

        if normalized_statuses & {"processing", "preprocessed"}:
            return age >= LIGHTRAG_STALE_PROCESSING_THRESHOLD

        return False

    def _has_ready_local_content(self, document_id: str, doc_info: Dict) -> bool:
        content_record = self._content_repository().get(document_id) or {}
        extraction_status = str(
            content_record.get("extraction_status")
            or doc_info.get("extraction_status")
            or ""
        ).lower()
        if extraction_status != "ready":
            return False
        return bool(
            str(content_record.get("full_content") or "").strip()
            or str(content_record.get("preview_content") or "").strip()
            or str(doc_info.get("preview_content") or "").strip()
        )

    @staticmethod
    def _is_lightrag_local_only_failure(ingest_error: str) -> bool:
        normalized_error = str(ingest_error or "").strip().lower()
        return any(marker in normalized_error for marker in LIGHTRAG_LOCAL_ONLY_FAILURE_MARKERS)

    def _maybe_recover_stale_remote_status(
        self,
        doc_info: Dict,
        remote_doc: Dict,
        normalized_statuses: set[str],
        *,
        now: str,
    ) -> None:
        if not self._is_stale_remote_status(doc_info, remote_doc, normalized_statuses):
            return

        try:
            pipeline_status = self._run_coroutine(self.lightrag_client.health()) or {}
        except Exception as exc:
            logger.warning(
                "document_ingest_pipeline_status_sync_failed document_id={} track_id={} error={}",
                doc_info.get("id"),
                doc_info.get("lightrag_track_id"),
                str(exc),
            )
            return

        pipeline_busy = bool(pipeline_status.get("busy") or pipeline_status.get("pipeline_busy"))
        if pipeline_busy:
            return

        try:
            self._run_coroutine(self.lightrag_client.reprocess_failed_documents())
            logger.info(
                "document_ingest_reprocess_requested document_id={} track_id={} statuses={}",
                doc_info.get("id"),
                doc_info.get("lightrag_track_id"),
                sorted(normalized_statuses),
            )
        except Exception as exc:
            logger.warning(
                "document_ingest_reprocess_failed document_id={} track_id={} error={}",
                doc_info.get("id"),
                doc_info.get("lightrag_track_id"),
                str(exc),
            )
        finally:
            self._update_ingest_status(
                doc_info["id"],
                ingest_status=str(doc_info.get("ingest_status") or "queued").lower() or "queued",
                ingest_error=doc_info.get("ingest_error"),
                lightrag_track_id=doc_info.get("lightrag_track_id"),
                lightrag_doc_id=remote_doc.get("id") or doc_info.get("lightrag_doc_id"),
                last_status_sync_at=now,
            )

    @staticmethod
    def _preserve_remote_wait_started_at(
        doc_info: Dict,
        *,
        target_status: str,
        now: str,
    ) -> str:
        current_status = str(doc_info.get("ingest_status") or "").strip().lower()
        current_sync_at = str(doc_info.get("last_status_sync_at") or "").strip()
        if current_status == target_status and current_sync_at:
            return current_sync_at
        return now

    @staticmethod
    def _is_lightrag_unsupported_failure(file_type: str, ingest_error: str) -> bool:
        normalized_file_type = str(file_type or "").strip().lower()
        normalized_error = str(ingest_error or "").strip().lower()
        return (
            bool(normalized_file_type and normalized_file_type not in LIGHTRAG_SUPPORTED_EXTENSIONS)
            or LIGHTRAG_UNSUPPORTED_ERROR_MARKER in normalized_error
        )

    def _sync_duplicate_remote_ingest_status(
        self,
        doc_info: Dict,
        remote_doc: Dict,
        now: str,
    ) -> Dict:
        metadata = remote_doc.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        original_track_id = str(metadata.get("original_track_id") or "").strip()
        original_doc_id = str(metadata.get("original_doc_id") or "").strip()
        duplicate_error = str(remote_doc.get("error_msg") or "").strip() or "Content already exists"

        if not original_track_id:
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="failed",
                ingest_error=duplicate_error,
                lightrag_doc_id=original_doc_id or remote_doc.get("id"),
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        try:
            original_payload = self._run_coroutine(
                self.lightrag_client.get_track_status(original_track_id)
            ) or {}
        except Exception as exc:
            logger.warning(
                "duplicate_ingest_original_track_status_sync_failed document_id={} track_id={} original_track_id={} error={}",
                doc_info.get("id"),
                doc_info.get("lightrag_track_id"),
                original_track_id,
                str(exc),
            )
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="processing",
                ingest_error=None,
                lightrag_track_id=original_track_id,
                lightrag_doc_id=original_doc_id or None,
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        original_documents = [
            item for item in (original_payload.get("documents") or []) if isinstance(item, dict)
        ]
        original_remote_doc = {}
        if original_doc_id:
            original_remote_doc = next(
                (item for item in original_documents if item.get("id") == original_doc_id),
                {},
            )
        if not original_remote_doc and original_documents:
            original_remote_doc = next(
                (item for item in original_documents if item.get("id")),
                original_documents[0],
            ) or {}

        original_status = self._normalize_lightrag_doc_status(original_remote_doc.get("status"))
        resolved_remote_doc_id = (
            original_remote_doc.get("id")
            or original_doc_id
            or remote_doc.get("id")
        )

        if original_status == "processed":
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="ready",
                ingest_error=None,
                lightrag_track_id=original_track_id,
                lightrag_doc_id=resolved_remote_doc_id,
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if original_status in {"processing", "preprocessed"}:
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="processing",
                ingest_error=None,
                lightrag_track_id=original_track_id,
                lightrag_doc_id=resolved_remote_doc_id,
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if original_status == "pending":
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="queued",
                ingest_error=None,
                lightrag_track_id=original_track_id,
                lightrag_doc_id=resolved_remote_doc_id,
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if original_status == "failed":
            try:
                self._run_coroutine(self.lightrag_client.reprocess_failed_documents())
            except Exception as exc:
                logger.warning(
                    "duplicate_ingest_reprocess_failed document_id={} original_track_id={} error={}",
                    doc_info.get("id"),
                    original_track_id,
                    str(exc),
                )
                self._update_ingest_status(
                    doc_info["id"],
                    ingest_status="failed",
                    ingest_error=str(original_remote_doc.get("error_msg") or duplicate_error),
                    lightrag_track_id=original_track_id,
                    lightrag_doc_id=resolved_remote_doc_id,
                    last_status_sync_at=now,
                )
                return self._get_document_info(doc_info["id"]) or doc_info

            self._update_ingest_status(
                doc_info["id"],
                ingest_status="processing",
                ingest_error=None,
                lightrag_track_id=original_track_id,
                lightrag_doc_id=resolved_remote_doc_id,
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        self._update_ingest_status(
            doc_info["id"],
            ingest_status="processing",
            ingest_error=None,
            lightrag_track_id=original_track_id,
            lightrag_doc_id=resolved_remote_doc_id,
            last_status_sync_at=now,
        )
        return self._get_document_info(doc_info["id"]) or doc_info

    def _sync_processing_ingest_status(self, doc_info: Dict) -> Dict:
        if not isinstance(doc_info, dict):
            return doc_info

        ingest_status = str(doc_info.get("ingest_status") or "").lower()
        track_id = str(doc_info.get("lightrag_track_id") or "").strip()
        if ingest_status not in {"queued", "processing", "failed"} or not track_id:
            return doc_info

        try:
            payload = self._run_coroutine(self.lightrag_client.get_track_status(track_id)) or {}
        except Exception as exc:
            logger.warning(
                "document_ingest_track_status_sync_failed document_id={} track_id={} error={}",
                doc_info.get("id"),
                track_id,
                str(exc),
            )
            return doc_info

        documents = list(payload.get("documents") or [])
        if not documents:
            return doc_info

        statuses = {
            self._normalize_lightrag_doc_status(item.get("status"))
            for item in documents
            if isinstance(item, dict)
        }
        remote_doc = next((item for item in documents if isinstance(item, dict) and item.get("id")), {}) or {}
        now = datetime.now().isoformat()

        if "failed" in statuses:
            metadata = remote_doc.get("metadata")
            if isinstance(metadata, dict) and metadata.get("is_duplicate"):
                return self._sync_duplicate_remote_ingest_status(doc_info, remote_doc, now)

            ingest_error = next(
                (
                    str(item.get("error_msg") or "").strip()
                    for item in documents
                    if isinstance(item, dict) and str(item.get("error_msg") or "").strip()
                ),
                "LightRAG processing failed",
            )
            if self._is_lightrag_unsupported_failure(doc_info.get("file_type", ""), ingest_error):
                self._update_ingest_status(
                    doc_info["id"],
                    ingest_status="local_only",
                    ingest_error=None,
                    lightrag_track_id=None,
                    lightrag_doc_id=None,
                    last_status_sync_at=now,
                )
                return self._get_document_info(doc_info["id"]) or doc_info
            if (
                self._is_lightrag_local_only_failure(ingest_error)
                and self._has_ready_local_content(doc_info["id"], doc_info)
            ):
                self._update_ingest_status(
                    doc_info["id"],
                    ingest_status="local_only",
                    ingest_error=ingest_error,
                    lightrag_doc_id=remote_doc.get("id"),
                    last_status_sync_at=now,
                )
                return self._get_document_info(doc_info["id"]) or doc_info
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="failed",
                ingest_error=ingest_error,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if statuses and statuses.issubset({"processed"}):
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="ready",
                ingest_error=None,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if statuses & {"processing", "preprocessed"}:
            self._maybe_recover_stale_remote_status(
                doc_info,
                remote_doc,
                statuses,
                now=now,
            )
            sync_started_at = self._preserve_remote_wait_started_at(
                doc_info,
                target_status="processing",
                now=now,
            )
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="processing",
                ingest_error=None,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=sync_started_at,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if statuses and statuses.issubset({"pending"}):
            self._maybe_recover_stale_remote_status(
                doc_info,
                remote_doc,
                statuses,
                now=now,
            )
            sync_started_at = self._preserve_remote_wait_started_at(
                doc_info,
                target_status="queued",
                now=now,
            )
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="queued",
                ingest_error=None,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=sync_started_at,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if statuses & {"pending"}:
            self._maybe_recover_stale_remote_status(
                doc_info,
                remote_doc,
                statuses,
                now=now,
            )
            sync_started_at = self._preserve_remote_wait_started_at(
                doc_info,
                target_status="processing",
                now=now,
            )
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="processing",
                ingest_error=None,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=sync_started_at,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        return doc_info

    @staticmethod
    def _initial_batch_import_status() -> Dict:
        return {
            "job_id": None,
            "state": "idle",
            "total": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "remaining": 0,
            "current_document_ids": [],
            "started_at": None,
            "finished_at": None,
            "last_error": None,
            "concurrency": 0,
            "interval_seconds": 0.0,
            "include_failed": False,
            "limit": 0,
            "already_running": False,
        }

    def upload(self, filename: str, file_stream) -> Dict:
        logger.info("document_upload_started filename={}", filename)
        # 0.1 路径遍历防护：只取纯文件名，剥离任何目录部分
        safe_name = Path(filename).name
        ext = os.path.splitext(safe_name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AppServiceError(2001, f"不支持的文件类型，仅支持：{', '.join(ALLOWED_EXTENSIONS)}")

        type_subdir = EXTENSION_TO_DIR.get(ext, "other")
        target_dir = self.doc_dir / type_subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # 实际存储使用 UUID 文件名，保留原始扩展名；metadata 保留原始 safe_name 供展示
        stored_stem = _uuid.uuid4().hex
        file_path = target_dir / f"{stored_stem}{ext}"
        counter = 1
        while file_path.exists():
            file_path = target_dir / f"{stored_stem}_{counter}{ext}"
            counter += 1

        # 流式写入磁盘，不一次性读入内存（支持大文件）
        try:
            with open(file_path, "wb") as handle:
                shutil.copyfileobj(file_stream, handle)
        except Exception as e:
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1002, f"文件保存失败: {e}")
        logger.info("document_file_persisted filename={} path={}", safe_name, file_path)

        # 写入后再校验大小
        if file_path.stat().st_size > MAX_FILE_SIZE:
            os.remove(file_path)
            raise AppServiceError(2002, f"文件过大，最大支持{MAX_FILE_SIZE // 1024 // 1024}MB")

        document_id = str(_uuid.uuid4())
        mtime = file_path.stat().st_mtime
        now = datetime.now().isoformat()
        ingest_status = "queued" if self._supports_lightrag_ingest(ext) else "local_only"
        doc_info = {
            "id": document_id,
            "filename": safe_name,
            "filepath": str(file_path),
            "file_type": ext,
            "preview_content": "",
            "full_content_length": 0,
            "parser_name": None,
            "extraction_status": "pending",
            "created_at": mtime,
            "created_at_iso": datetime.fromtimestamp(mtime).isoformat(),
            "updated_at": now,
            "ingest_status": ingest_status,
            "ingest_error": None,
            "lightrag_track_id": None,
            "lightrag_doc_id": None,
            "last_status_sync_at": None,
            "local_index_status": "queued",
            "local_index_error": None,
        }
        if not self._document_repository().upsert(doc_info):
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1002, "文档元数据保存失败")
        logger.info("document_metadata_persisted document_id={} filename={}", document_id, safe_name)
        self._mark_stage(document_id, "content_extract", status="queued", payload={})
        self._mark_stage(document_id, "local_preview_index", status="queued", payload={})
        self._mark_stage(document_id, "rag_ingest", status="queued", payload={})

        if self.enqueue_background:
            self._enqueue_document_pipeline(document_id)

        return self._hydrate_document(doc_info)

    def _enqueue_document_pipeline(self, document_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(self.process_local_index, document_id))
            loop.create_task(self.process_pending_ingest(document_id))
        except RuntimeError:
            logger.warning("no_running_loop_for_document_pipeline document_id={}", document_id)

    def _enqueue_ingest(self, document_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.process_pending_ingest(document_id))
        except RuntimeError:
            logger.warning("no_running_loop_for_ingest_enqueue document_id={}", document_id)

    def process_local_index(
        self,
        document_id: str,
        force: bool = False,
        build_block_index: bool = False,
    ) -> Dict:
        doc_info = self.get_document(document_id)
        current_status = str(doc_info.get("local_index_status") or "").lower()
        if current_status == "ready" and not force:
            return doc_info

        now = datetime.now().isoformat()
        self._update_document_info(
            document_id,
            {
                "local_index_status": "processing",
                "local_index_error": None,
                "extraction_status": "processing",
                "updated_at": now,
            },
        )
        self._mark_stage(document_id, "content_extract", status="processing", payload={})
        self._mark_stage(document_id, "local_preview_index", status="processing", payload={})
        processing_doc = self.get_document(document_id)

        try:
            extraction = self.extraction_service.extract(processing_doc.get("filepath", ""))
            if not extraction.success:
                raise RuntimeError(extraction.error or "document extraction failed")

            saved = self._content_repository().save(
                document_id,
                full_content=extraction.content,
                preview_content=extraction.preview_content,
                extraction_status="ready",
                parser_name=extraction.parser_name,
                extraction_error=None,
            )
            if not saved:
                raise RuntimeError("document content save failed")

            self._mark_stage(
                document_id,
                "content_extract",
                status="ready",
                payload={
                    "content_length": extraction.full_content_length,
                    "parser_name": extraction.parser_name,
                },
            )

            local_index_error = None
            if build_block_index:
                index_result = self.indexing_service.index_document(document_id, force=True)
                if (index_result or {}).get("block_index_status") == "failed":
                    local_index_error = (index_result or {}).get("error") or "reader block index failed"

            self._update_document_info(
                document_id,
                {
                    "local_index_status": "ready",
                    "local_index_error": local_index_error,
                    "extraction_status": "ready",
                    "parser_name": extraction.parser_name,
                    "preview_content": extraction.preview_content,
                    "full_content_length": extraction.full_content_length,
                    "updated_at": datetime.now().isoformat(),
                },
            )
            self._mark_stage(
                document_id,
                "local_preview_index",
                status="ready",
                payload={
                    "content_length": extraction.full_content_length,
                    "parser_name": extraction.parser_name,
                },
            )
            self._sync_aggregate_status_fields(document_id)
            try:
                get_search_cache().invalidate_all()
            except Exception:
                pass
            return self.get_document(document_id)
        except Exception as exc:
            error_message = str(exc)
            logger.warning("document_local_index_failed document_id={} error={}", document_id, error_message)
            self._update_document_info(
                document_id,
                {
                    "local_index_status": "failed",
                    "local_index_error": error_message,
                    "extraction_status": "failed",
                    "extraction_error": error_message,
                    "updated_at": datetime.now().isoformat(),
                },
            )
            self._mark_stage(
                document_id,
                "content_extract",
                status="failed",
                error_code="extract_failed",
                error_message=error_message,
                payload={},
            )
            self._mark_stage(
                document_id,
                "local_preview_index",
                status="failed",
                error_code="extract_failed",
                error_message=error_message,
                payload={},
            )
            self._sync_aggregate_status_fields(document_id)
            return self.get_document(document_id)

    async def process_pending_ingest(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        if (doc_info.get("ingest_status") or "") not in {"queued", "failed", "processing", "local_only"}:
            return doc_info
        if not self._supports_lightrag_ingest(doc_info.get("file_type", "")):
            if (doc_info.get("ingest_status") or "").lower() != "local_only":
                self._update_ingest_status(
                    document_id,
                    ingest_status="local_only",
                    ingest_error=None,
                    lightrag_track_id=None,
                    lightrag_doc_id=None,
                    last_status_sync_at=datetime.now().isoformat(),
                )
            self._mark_stage(document_id, "rag_ingest", status="deferred", payload={})
            self._sync_aggregate_status_fields(document_id)
            return self.get_document(document_id)

        stage_map = self._load_stage_map(document_id)
        content_record = self._content_repository().get(document_id) or {}
        content_length = len(str((content_record.get("full_content") or "")).strip())
        estimated_chunks = max(1, content_length // 1200) if content_length else 0
        profile = build_document_profile(
            doc_info.get("filename", ""),
            doc_info.get("file_type", ""),
            content_length,
            estimated_chunks,
        )
        if self.rag_circuit_breaker.is_open():
            self._mark_stage(
                document_id,
                "rag_ingest",
                status="deferred",
                error_code="dependency_degraded",
                error_message="waiting for embedding or lightrag recovery",
                retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
                payload={"profile": profile},
            )
            self._sync_aggregate_status_fields(document_id)
            return self.get_document(document_id)
        if profile["defer_rag"]:
            self._mark_stage(
                document_id,
                "rag_ingest",
                status="deferred",
                error_code=None,
                error_message=None,
                retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
                payload={"profile": profile},
            )
            self._sync_aggregate_status_fields(document_id)
            return self.get_document(document_id)

        self._update_ingest_status(
            document_id,
            ingest_status="processing",
            ingest_error=None,
            last_status_sync_at=datetime.now().isoformat(),
        )
        self._mark_stage(
            document_id,
            "rag_ingest",
            status="processing",
            retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
            payload={"profile": profile},
        )
        processing_doc = self.get_document(document_id)

        try:
            await self.local_embedding_runtime.ensure_ready()
            result = await self.lightrag_client.upload_file(
                processing_doc.get("filepath", ""),
                processing_doc.get("filename", ""),
            )
            status = str(result.get("status") or "").lower()
            track_id = result.get("track_id") or result.get("id")
            if status == "duplicated" and track_id:
                self.rag_circuit_breaker.record_failure("duplicated")
                self._update_ingest_status(
                    document_id,
                    ingest_status="failed",
                    ingest_error=result.get("message") or "Content already exists",
                    lightrag_track_id=track_id,
                    last_status_sync_at=datetime.now().isoformat(),
                )
                self._mark_stage(
                    document_id,
                    "rag_ingest",
                    status="failed",
                    error_code="duplicated",
                    error_message=result.get("message") or "Content already exists",
                    retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0) + 1,
                    payload={"track_id": track_id, "profile": profile},
                )
                self._sync_aggregate_status_fields(document_id)
                try:
                    get_search_cache().invalidate_all()
                except Exception:
                    pass
                return self.get_document(document_id)
            if status in {"failed", "error"}:
                raise RuntimeError(result.get("message") or "LightRAG upload failed")
            self.rag_circuit_breaker.record_success()
            self._update_ingest_status(
                document_id,
                ingest_status="processing",
                ingest_error=None,
                lightrag_track_id=track_id,
                last_status_sync_at=datetime.now().isoformat(),
            )
            self._mark_stage(
                document_id,
                "rag_ingest",
                status="processing",
                retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
                payload={"track_id": track_id, "profile": profile},
            )
            self._sync_aggregate_status_fields(document_id)
            try:
                get_search_cache().invalidate_all()
            except Exception:
                pass
            return self.get_document(document_id)
        except Exception as exc:
            error_message = str(exc)
            logger.warning("document_ingest_failed document_id={} error={}", document_id, error_message)
            error_code = "embedding_unready" if "embedding" in error_message.lower() else "rag_ingest_failed"
            self.rag_circuit_breaker.record_failure(error_code)
            self._update_ingest_status(
                document_id,
                ingest_status="failed",
                ingest_error=error_message,
                last_status_sync_at=datetime.now().isoformat(),
            )
            self._mark_stage(
                document_id,
                "rag_ingest",
                status="failed",
                error_code=error_code,
                error_message=error_message,
                retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0) + 1,
                payload={"track_id": None, "profile": profile},
            )
            self._sync_aggregate_status_fields(document_id)
            return self.get_document(document_id)

    def _list_batch_import_candidates(self, *, limit: int, include_failed: bool) -> List[Dict]:
        statuses = {"local_only"}
        if include_failed:
            statuses.add("failed")

        documents = [
            item
            for item in (self._document_repository().list_all() or [])
            if (
                isinstance(item, dict)
                and (item.get("ingest_status") or "").lower() in statuses
                and self._supports_lightrag_ingest(item.get("file_type", ""))
            )
        ]
        documents.sort(
            key=lambda item: (
                str(item.get("updated_at") or item.get("created_at_iso") or ""),
                str(item.get("filename") or ""),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        if limit > 0:
            documents = documents[:limit]
        return documents

    def _set_batch_import_status(self, **updates) -> None:
        self._batch_import_status.update(updates)
        total = int(self._batch_import_status.get("total") or 0)
        processed = int(self._batch_import_status.get("processed") or 0)
        self._batch_import_status["remaining"] = max(total - processed, 0)

    def get_batch_import_status(self) -> Dict:
        payload = dict(self._batch_import_status)
        payload["current_document_ids"] = list(payload.get("current_document_ids") or [])
        return payload

    def start_local_only_batch_import(
        self,
        *,
        limit: int = 100,
        concurrency: int = 1,
        interval_seconds: float = 0.5,
        include_failed: bool = False,
    ) -> Dict:
        normalized_limit = max(int(limit or 0), 0)
        normalized_concurrency = max(int(concurrency or 1), 1)
        normalized_interval = max(float(interval_seconds or 0), 0.0)

        if self._batch_import_task is not None and not self._batch_import_task.done():
            payload = self.get_batch_import_status()
            payload["already_running"] = True
            return payload

        candidates = self._list_batch_import_candidates(
            limit=normalized_limit,
            include_failed=include_failed,
        )
        candidate_ids = [item.get("id") for item in candidates if item.get("id")]
        started_at = datetime.now().isoformat()
        self._batch_import_status = self._initial_batch_import_status()
        self._set_batch_import_status(
            job_id=_uuid.uuid4().hex,
            state="running" if candidate_ids else "completed",
            total=len(candidate_ids),
            processed=0,
            succeeded=0,
            failed=0,
            current_document_ids=[],
            started_at=started_at,
            finished_at=None if candidate_ids else started_at,
            last_error=None,
            concurrency=normalized_concurrency,
            interval_seconds=normalized_interval,
            include_failed=include_failed,
            limit=normalized_limit,
            already_running=False,
        )

        if not candidate_ids:
            self._batch_import_task = None
            return self.get_batch_import_status()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            self._set_batch_import_status(
                state="failed",
                finished_at=datetime.now().isoformat(),
                last_error="后台导入任务需要运行中的事件循环",
            )
            raise AppServiceError(1002, "后台导入任务需要运行中的事件循环") from exc

        self._batch_import_task = loop.create_task(
            self._run_local_only_batch_import(
                candidate_ids,
                concurrency=normalized_concurrency,
                interval_seconds=normalized_interval,
            )
        )
        return self.get_batch_import_status()

    async def _run_local_only_batch_import(
        self,
        document_ids: List[str],
        *,
        concurrency: int,
        interval_seconds: float,
    ) -> None:
        queue: asyncio.Queue[str] = asyncio.Queue()
        for document_id in document_ids:
            queue.put_nowait(document_id)

        async def worker() -> None:
            while True:
                try:
                    document_id = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                current_document_ids = list(self._batch_import_status.get("current_document_ids") or [])
                if document_id not in current_document_ids:
                    current_document_ids.append(document_id)
                    self._set_batch_import_status(current_document_ids=current_document_ids)

                try:
                    result = await self.process_pending_ingest(document_id)
                    success = (result.get("ingest_status") or "") != "failed"
                    failed = int(self._batch_import_status.get("failed") or 0)
                    succeeded = int(self._batch_import_status.get("succeeded") or 0)
                    if success:
                        succeeded += 1
                    else:
                        failed += 1
                    self._set_batch_import_status(
                        processed=int(self._batch_import_status.get("processed") or 0) + 1,
                        succeeded=succeeded,
                        failed=failed,
                        last_error=None if success else result.get("ingest_error"),
                    )
                except Exception as exc:
                    self._set_batch_import_status(
                        processed=int(self._batch_import_status.get("processed") or 0) + 1,
                        failed=int(self._batch_import_status.get("failed") or 0) + 1,
                        last_error=str(exc),
                    )
                finally:
                    current_document_ids = [
                        item
                        for item in (self._batch_import_status.get("current_document_ids") or [])
                        if item != document_id
                    ]
                    self._set_batch_import_status(current_document_ids=current_document_ids)
                    queue.task_done()
                    if interval_seconds > 0:
                        await asyncio.sleep(interval_seconds)

        try:
            workers = [asyncio.create_task(worker()) for _ in range(max(concurrency, 1))]
            await asyncio.gather(*workers)
            self._set_batch_import_status(
                state="completed",
                finished_at=datetime.now().isoformat(),
                current_document_ids=[],
            )
        except Exception as exc:
            logger.warning("local_only_batch_import_failed error={}", str(exc))
            self._set_batch_import_status(
                state="failed",
                finished_at=datetime.now().isoformat(),
                current_document_ids=[],
                last_error=str(exc),
            )
            raise
        finally:
            self._batch_import_task = None

    async def wait_for_batch_import(self) -> None:
        if self._batch_import_task is not None:
            await self._batch_import_task

    def retry_ingest(self, document_id: str) -> Dict:
        self.get_document(document_id)
        self._update_document_info(
            document_id,
            {
                "ingest_status": "queued",
                "ingest_error": None,
                "lightrag_track_id": None,
                "lightrag_doc_id": None,
                "last_status_sync_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        )
        if self.enqueue_background:
            self._enqueue_ingest(document_id)
        return self.get_document(document_id)

    def retry_rag_stage(self, document_id: str) -> Dict:
        self.get_document(document_id)
        stage_map = self._load_stage_map(document_id)
        self._mark_stage(
            document_id,
            "rag_ingest",
            status="queued",
            error_code=None,
            error_message=None,
            retry_count=stage_map.get("rag_ingest", {}).get("retry_count", 0),
            payload=stage_map.get("rag_ingest", {}).get("payload", {}),
        )
        aggregated = self._sync_aggregate_status_fields(document_id)
        self.rag_circuit_breaker.record_success()
        if self.enqueue_background:
            self._enqueue_ingest(document_id)
        return {"document_id": document_id, "rag_ingest": "queued", **aggregated}

    def list_documents(self, page: int, page_size: int) -> Dict:
        logger.info("query_documents page={} page_size={}", page, page_size)
        try:
            all_docs = list(get_all_documents() or []) if self.document_repository is None else list(self._document_repository().list_all() or [])
        except Exception as exc:
            logger.opt(exception=exc).error("query_documents_failed page={} page_size={}", page, page_size)
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

        total = len(all_docs)
        start = (page - 1) * page_size
        end = start + page_size
        items: List[Dict] = []
        for item in all_docs[start:end]:
            if not isinstance(item, dict):
                logger.warning("skip_invalid_document_row row_type={}", type(item).__name__)
                continue
            try:
                synced_item = self._sync_processing_ingest_status(item)
                items.append(self._hydrate_document(synced_item))
            except Exception as exc:
                logger.opt(exception=exc).error(
                    "hydrate_document_failed document_id={} filename={}",
                    item.get("id"),
                    item.get("filename"),
                )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        }

    def stats(self) -> Dict:
        logger.info("query_document_stats")
        try:
            all_docs = list(get_all_documents() or []) if self.document_repository is None else list(self._document_repository().list_all() or [])
        except Exception as exc:
            logger.opt(exception=exc).error("query_document_stats_failed")
            return {"total": 0, "categorized": 0, "uncategorized": 0}

        valid_docs = [item for item in all_docs if isinstance(item, dict)]
        total = len(valid_docs)
        categorized = sum(
            1
            for item in valid_docs
            if str(item.get("classification_result") or "").strip()
        )
        return {
            "total": total,
            "categorized": categorized,
            "uncategorized": max(total - categorized, 0),
        }

    def get_document(self, document_id: str) -> Dict:
        doc_info = self._get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        doc_info = self._sync_processing_ingest_status(doc_info)
        return self._hydrate_document(doc_info)

    def get_runtime_health(self) -> Dict:
        return {
            "rag_circuit": self.rag_circuit_breaker.snapshot(),
        }

    def get_document_payload(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        content_record = self._content_repository().get(document_id) or {}
        segments = self._segment_repository().list(document_id)
        artifacts = self._artifact_repository().list(document_id)
        return {
            **doc_info,
            "content_record": content_record,
            "segments": segments,
            "artifacts": artifacts,
        }

    def get_reader_payload(
        self,
        document_id: str,
        query: str = "",
        anchor_block_id: Optional[str] = None,
    ) -> Dict:
        doc_info = self.get_document(document_id)
        content_record = self._content_repository().get(document_id) or {}
        blocks = self._build_reader_blocks(document_id, content_record)
        keywords = self._extract_reader_terms(query)

        total_matches = 0
        resolved_anchor = {
            "block_id": anchor_block_id,
            "block_index": 0,
            "match_index": 0,
            "start": 0,
            "end": 0,
            "term": keywords[0] if keywords else None,
        }
        resolved_anchor_score = (-1, -1)
        hydrated_blocks = []

        for block in blocks:
            matches = self._find_text_matches(block["text"], keywords)
            total_matches += len(matches)
            block_payload = {**block, "matches": matches}
            hydrated_blocks.append(block_payload)

            anchor_score = (len(matches), -block["block_index"])
            should_replace_anchor = False
            if anchor_block_id and block["block_id"] == anchor_block_id:
                should_replace_anchor = True
            elif not anchor_block_id and matches and anchor_score > resolved_anchor_score:
                should_replace_anchor = True

            if should_replace_anchor:
                first_match = matches[0] if matches else {"start": 0, "end": 0, "term": None}
                resolved_anchor = {
                    "block_id": block["block_id"],
                    "block_index": block["block_index"],
                    "match_index": 0,
                    "start": first_match["start"],
                    "end": first_match["end"],
                    "term": first_match["term"],
                }
                resolved_anchor_score = anchor_score

        if not resolved_anchor.get("block_id") and hydrated_blocks:
            first_block = hydrated_blocks[0]
            resolved_anchor["block_id"] = first_block["block_id"]
            resolved_anchor["block_index"] = first_block["block_index"]

        return {
            "document_id": document_id,
            "filename": doc_info.get("filename", ""),
            "file_type": doc_info.get("file_type", ""),
            "classification_result": doc_info.get("classification_result"),
            "created_at_iso": doc_info.get("created_at_iso"),
            "parser_name": content_record.get("parser_name") or doc_info.get("parser_name"),
            "extraction_status": content_record.get("extraction_status") or doc_info.get("extraction_status"),
            "query": query or "",
            "keywords": keywords,
            "total_matches": total_matches,
            "best_anchor": resolved_anchor,
            "blocks": hydrated_blocks,
        }

    def delete_document(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        file_path = Path(doc_info.get("filepath", ""))
        file_deleted = False

        try:
            if file_path.exists():
                os.remove(file_path)
            file_deleted = True
        except Exception:
            file_deleted = True

        if not delete_document(document_id):
            raise AppServiceError(1004, f"文档ID: {document_id}")

        # 3.1/3.2 删除文档后使搜索缓存失效
        try:
            get_search_cache().invalidate_all()
        except Exception:
            pass

        return {"document_id": document_id, "file_deleted": file_deleted}

    def rechunk(self, document_id: str, use_refiner: bool) -> Dict:
        self.get_document(document_id)
        _ = use_refiner
        result = self.indexing_service.index_document(document_id, force=True)
        if (result or {}).get("block_index_status") != "ready":
            raise AppServiceError(1003, (result or {}).get("error", "重新构建 block 索引失败"))
        return get_block_status(document_id)

    def get_chunk_status(self, document_id: str) -> Dict:
        chunk_status = get_block_status(document_id)
        if not chunk_status.get("exists"):
            raise AppServiceError(1001, f"文档ID: {document_id}")
        return chunk_status

    def batch_rechunk(self, document_ids: List[str], use_refiner: bool) -> Dict:
        results = []
        _ = use_refiner
        for document_id in document_ids:
            try:
                self.get_document(document_id)
                result = self.indexing_service.index_document(document_id, force=True)
                success = (result or {}).get("block_index_status") == "ready"
                payload = {"document_id": document_id, "success": success}
                if not success and (result or {}).get("error"):
                    payload["error"] = result["error"]
                results.append(payload)
            except Exception as exc:
                results.append({"document_id": document_id, "success": False, "error": str(exc)})

        success_count = sum(1 for item in results if item["success"])
        return {"results": results, "total": len(results), "success_count": success_count}

    def list_local_index_candidates(self, *, limit: int = 100, include_failed: bool = False) -> List[str]:
        documents = list(self._document_repository().list_all() or [])
        candidates: List[str] = []
        for item in documents:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            status = str(item.get("local_index_status") or "").lower()
            has_content = bool(str(item.get("preview_content") or "").strip())
            if status in {"queued", "processing", ""} or not has_content:
                candidates.append(item["id"])
            elif include_failed and status == "failed":
                candidates.append(item["id"])
        if limit > 0:
            candidates = candidates[:limit]
        return candidates

    def backfill_local_index(
        self,
        *,
        limit: int = 100,
        include_failed: bool = False,
        build_block_index: bool = False,
    ) -> Dict:
        candidate_ids = self.list_local_index_candidates(limit=limit, include_failed=include_failed)
        results = []
        for document_id in candidate_ids:
            result = self.process_local_index(
                document_id,
                force=include_failed,
                build_block_index=build_block_index,
            )
            results.append(
                {
                    "document_id": document_id,
                    "local_index_status": result.get("local_index_status"),
                    "local_index_error": result.get("local_index_error"),
                }
            )
        success_count = sum(1 for item in results if item.get("local_index_status") == "ready")
        return {"results": results, "total": len(results), "success_count": success_count}

    def _build_reader_blocks(self, document_id: str, content_record: Dict) -> List[Dict]:
        artifact = self._artifact_repository().get(document_id, "reader_blocks") or {}
        artifact_blocks = (artifact.get("payload") or {}).get("blocks") or []
        if artifact_blocks:
            return [
                {
                    "block_id": block.get("block_id") or f"{document_id}#{block.get('block_index', index)}",
                    "block_index": block.get("block_index", index),
                    "block_type": block.get("block_type") or "paragraph",
                    "heading_path": list(block.get("heading_path") or []),
                    "page_number": block.get("page_number"),
                    "text": block.get("text", ""),
                }
                for index, block in enumerate(sorted(artifact_blocks, key=lambda item: item.get("block_index", 0)))
                if block.get("text")
            ]

        segments = self._segment_repository().list(document_id)
        if segments:
            return [
                {
                    "block_id": segment.get("segment_id") or f"{document_id}#{segment.get('segment_index', index)}",
                    "block_index": segment.get("segment_index", index),
                    "block_type": "paragraph",
                    "heading_path": [segment.get("title")] if segment.get("title") else [],
                    "text": segment.get("content", ""),
                    "page_number": segment.get("page_number"),
                }
                for index, segment in enumerate(segments)
                if segment.get("content")
            ]

        full_content = content_record.get("full_content") or content_record.get("preview_content") or ""
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n|\n", full_content) if item.strip()]
        if not paragraphs and full_content.strip():
            paragraphs = [full_content.strip()]

        return [
            {
                "block_id": f"{document_id}#{index}",
                "block_index": index,
                "block_type": "paragraph",
                "heading_path": [],
                "text": paragraph,
                "page_number": None,
            }
            for index, paragraph in enumerate(paragraphs)
        ]

    def _extract_reader_terms(self, query: str) -> List[str]:
        if not query or not query.strip():
            return []

        parser = get_query_parser()
        parsed = parser.parse(query)
        ordered_terms: List[str] = []
        for item in [*parsed.exact_phrases, *parsed.include_terms, *parsed.fuzzy_terms]:
            value = (item or "").strip()
            if value and value not in ordered_terms:
                ordered_terms.append(value)

        normalized_query = query.strip()
        if normalized_query and normalized_query not in ordered_terms:
            ordered_terms.append(normalized_query)
        return sorted(ordered_terms, key=len, reverse=True)

    @staticmethod
    def _find_text_matches(text: str, terms: List[str]) -> List[Dict]:
        if not text or not terms:
            return []

        matches: List[Dict] = []
        for term in terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for item in pattern.finditer(text):
                candidate = {
                    "start": item.start(),
                    "end": item.end(),
                    "term": term,
                }
                if any(
                    existing["start"] == candidate["start"] and existing["end"] == candidate["end"]
                    for existing in matches
                ):
                    continue
                matches.append(candidate)
        matches.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
        return matches
