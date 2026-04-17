import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List

from app.core.logger import logger
from app.infra.repositories.document_artifact_repository import DocumentArtifactRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.vector_store import get_block_collection
from config import DATA_DIR
from utils.block_extractor import extract_structured_blocks


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _artifact_repository() -> DocumentArtifactRepository:
    return DocumentArtifactRepository(data_dir=DATA_DIR)


def get_document_info(document_id: str):
    return _document_repository().get(document_id)


def update_document_info(document_id: str, updated_info: Dict[str, Any]) -> bool:
    return _document_repository().update(document_id, updated_info)


def upsert_document_artifact(document_id: str, artifact_type: str, payload: Dict[str, Any]):
    return _artifact_repository().upsert(document_id, artifact_type, payload)


def get_all_documents():
    return _document_repository().list_all()


class IndexingService:
    READER_ARTIFACT_TYPE = "reader_blocks"
    SUPPORTED_BLOCK_FILE_TYPES = {".pdf", ".docx"}

    def audit_block_index(self, document_id: str = "") -> Dict[str, Any]:
        documents = self._load_documents(document_id)
        known_document_ids = {
            item.get("id")
            for item in documents
            if item.get("id")
        }
        collection = get_block_collection()
        block_snapshot = self._snapshot_all_blocks(collection)
        actual_counts = block_snapshot["counts"]

        reports: List[Dict[str, Any]] = []
        rebuild_candidates: List[str] = []
        for document in documents:
            doc_id = document.get("id")
            if not doc_id:
                continue

            status = (document.get("block_index_status") or "").strip().lower()
            expected_block_count = self._coerce_optional_int(document.get("block_count"))
            actual_block_count = actual_counts.get(doc_id, 0)
            rebuild_reasons: List[str] = []
            supports_block_index = self._supports_block_index(document)

            if supports_block_index and status and status != "ready":
                rebuild_reasons.append(f"status_{status}")
            if supports_block_index and actual_block_count == 0:
                if not (status == "ready" and expected_block_count == 0):
                    rebuild_reasons.append("missing_blocks")
            elif supports_block_index and expected_block_count is not None and expected_block_count != actual_block_count:
                rebuild_reasons.append("block_count_mismatch")

            report = {
                "document_id": doc_id,
                "filename": document.get("filename", ""),
                "filepath": document.get("filepath", ""),
                "block_index_status": status,
                "expected_block_count": expected_block_count,
                "actual_block_count": actual_block_count,
                "needs_rebuild": bool(rebuild_reasons),
                "rebuild_reasons": rebuild_reasons,
            }
            reports.append(report)
            if report["needs_rebuild"]:
                rebuild_candidates.append(doc_id)

        orphan_block_ids = [
            row_id
            for row_id, metadata in zip(block_snapshot["ids"], block_snapshot["metadatas"])
            if (metadata.get("document_id") or "") not in known_document_ids
        ]
        return {
            "documents": reports,
            "rebuild_candidates": rebuild_candidates,
            "orphan_block_ids": orphan_block_ids,
        }

    def list_rebuild_candidates(
        self,
        document_id: str = "",
        failed_only: bool = False,
        limit: int = 0,
        rebuild_all: bool = False,
    ) -> List[str]:
        if document_id:
            doc_info = get_document_info(document_id)
            return [document_id] if doc_info else []

        audit = self.audit_block_index()
        candidates: List[str] = []
        for report in audit["documents"]:
            if rebuild_all:
                candidates.append(report["document_id"])
                continue
            if failed_only:
                if report.get("block_index_status") == "failed":
                    candidates.append(report["document_id"])
                continue
            if report.get("needs_rebuild"):
                candidates.append(report["document_id"])

        if limit > 0:
            candidates = candidates[:limit]
        return candidates

    def cleanup_orphan_block_rows(self) -> List[str]:
        collection = get_block_collection()
        if collection is None:
            return []

        audit = self.audit_block_index()
        orphan_block_ids = list(audit.get("orphan_block_ids") or [])
        if orphan_block_ids:
            collection.delete(ids=orphan_block_ids)
        return orphan_block_ids

    def index_document(self, document_id: str, force: bool = False) -> Dict[str, Any]:
        started_at = perf_counter()
        logger.info("block_index_started document_id={} force={}", document_id, force)
        doc_info = get_document_info(document_id)
        if not doc_info:
            logger.warning("block_index_skipped_missing_document document_id={}", document_id)
            return {"document_id": document_id, "block_index_status": "failed", "error": "document not found"}

        block_collection = None
        old_snapshot = {"ids": [], "documents": [], "metadatas": []}
        new_ids = []
        try:
            extraction_started_at = perf_counter()
            block_payload = extract_structured_blocks(doc_info.get("filepath", ""), document_id)
            blocks = block_payload.get("blocks") or []
            logger.info(
                "block_extraction_completed document_id={} block_count={} duration_ms={:.2f}",
                document_id,
                len(blocks),
                (perf_counter() - extraction_started_at) * 1000,
            )
            block_collection = get_block_collection()
            if block_collection is None:
                raise RuntimeError("block collection unavailable")

            old_snapshot = self._snapshot_existing_blocks(block_collection, document_id)
            if old_snapshot["ids"]:
                block_collection.delete(ids=old_snapshot["ids"])

            ids = []
            documents = []
            metadatas = []
            indexed_at = datetime.now(timezone.utc).isoformat()

            for index, block in enumerate(blocks):
                block_id = block.get("block_id") or f"{document_id}:{block_payload.get('index_version', 'block-v1')}:{index}"
                ids.append(block_id)
                documents.append(block.get("text", ""))
                metadatas.append(self._build_block_metadata(doc_info, block_payload, block, document_id, indexed_at))

            vector_write_started_at = perf_counter()
            if ids:
                block_collection.add(documents=documents, metadatas=metadatas, ids=ids)
                new_ids = list(ids)
            logger.info(
                "block_vector_write_completed document_id={} block_count={} duration_ms={:.2f}",
                document_id,
                len(ids),
                (perf_counter() - vector_write_started_at) * 1000,
            )

            artifact_id = upsert_document_artifact(
                document_id,
                self.READER_ARTIFACT_TYPE,
                {
                    "index_version": block_payload.get("index_version"),
                    "indexed_content_hash": block_payload.get("indexed_content_hash"),
                    "block_count": len(blocks),
                    "blocks": blocks,
                },
            )
            if not artifact_id:
                raise RuntimeError("failed to persist reader artifact")

            update_document_info(
                document_id,
                {
                    "block_index_status": "ready",
                    "index_version": block_payload.get("index_version"),
                    "indexed_content_hash": block_payload.get("indexed_content_hash"),
                    "block_count": len(blocks),
                    "last_indexed_at": indexed_at,
                    "block_index_error": None,
                },
            )
            logger.info(
                "block_index_completed document_id={} block_count={} total_duration_ms={:.2f}",
                document_id,
                len(blocks),
                (perf_counter() - started_at) * 1000,
            )
            return {"document_id": document_id, "block_index_status": "ready"}
        except Exception as exc:
            self._rollback_blocks(block_collection, old_snapshot, new_ids)
            short_error = self._short_error(exc)
            logger.opt(exception=exc).error(
                "block_index_failed document_id={} total_duration_ms={:.2f}",
                document_id,
                (perf_counter() - started_at) * 1000,
            )
            update_document_info(
                document_id,
                {
                    "block_index_status": "failed",
                    "block_index_error": short_error,
                    "last_indexed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return {"document_id": document_id, "block_index_status": "failed", "error": short_error}

    def _build_block_metadata(
        self,
        doc_info: Dict[str, Any],
        block_payload: Dict[str, Any],
        block: Dict[str, Any],
        document_id: str,
        indexed_at: str,
    ) -> Dict[str, Any]:
        heading_path = block.get("heading_path") or []
        page_number = block.get("page_number")

        metadata: Dict[str, Any] = {
            "document_id": document_id,
            "filename": doc_info.get("filename", ""),
            "file_type": doc_info.get("file_type", ""),
            "file_type_family": self._derive_file_type_family(doc_info.get("file_type", "")),
            "source_parser": self._derive_source_parser(doc_info),
            "index_version": block_payload.get("index_version", ""),
            "indexed_content_hash": block_payload.get("indexed_content_hash", ""),
            "block_id": block.get("block_id", ""),
            "block_index": int(block.get("block_index", 0)),
            "block_type": block.get("block_type", "paragraph"),
            "heading_path": json.dumps(heading_path, ensure_ascii=False),
            "page_number": int(page_number) if isinstance(page_number, int) else -1,
            "last_indexed_at": indexed_at,
        }
        return metadata

    @staticmethod
    def _derive_file_type_family(file_type: str) -> str:
        ext = (file_type or "").lower().lstrip(".")
        family_map = {
            "pdf": "pdf",
            "doc": "word",
            "docx": "word",
            "ppt": "presentation",
            "pptx": "presentation",
            "xls": "spreadsheet",
            "xlsx": "spreadsheet",
            "csv": "spreadsheet",
            "txt": "text",
            "md": "text",
            "html": "web",
            "htm": "web",
            "eml": "email",
            "msg": "email",
        }
        return family_map.get(ext, "other")

    @staticmethod
    def _derive_source_parser(doc_info: Dict[str, Any]) -> str:
        parser_name = (doc_info.get("parser_name") or "").strip()
        if parser_name:
            return parser_name
        file_type = (doc_info.get("file_type") or "").strip().lstrip(".")
        if file_type:
            return file_type.lower()
        return "unknown"

    @staticmethod
    def _short_error(exc: Exception, max_len: int = 160) -> str:
        raw = str(exc).strip() or exc.__class__.__name__
        return raw[:max_len]

    @staticmethod
    def _coerce_optional_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _supports_block_index(cls, document: Dict[str, Any]) -> bool:
        file_type = str(document.get("file_type") or "").strip().lower()
        if not file_type:
            file_type = Path(str(document.get("filepath") or "")).suffix.lower()
        if file_type and not file_type.startswith("."):
            file_type = f".{file_type}"
        return file_type in cls.SUPPORTED_BLOCK_FILE_TYPES

    @staticmethod
    def _load_documents(document_id: str = "") -> List[Dict[str, Any]]:
        if document_id:
            doc_info = get_document_info(document_id)
            return [doc_info] if doc_info else []
        return get_all_documents()

    @staticmethod
    def _snapshot_all_blocks(block_collection) -> Dict[str, Any]:
        if block_collection is None:
            return {"ids": [], "metadatas": [], "counts": {}}

        existing = block_collection.get(include=["metadatas"])
        ids = list(existing.get("ids") or [])
        metadatas = list(existing.get("metadatas") or [])
        if len(metadatas) < len(ids):
            metadatas.extend([{}] * (len(ids) - len(metadatas)))

        counts: Dict[str, int] = {}
        for metadata in metadatas:
            document_id = (metadata or {}).get("document_id")
            if document_id:
                counts[document_id] = counts.get(document_id, 0) + 1

        return {"ids": ids, "metadatas": metadatas, "counts": counts}

    @staticmethod
    def _snapshot_existing_blocks(block_collection, document_id: str) -> Dict[str, Any]:
        existing = block_collection.get(where={"document_id": document_id}, include=["documents", "metadatas"])
        ids = list(existing.get("ids") or [])
        documents = list(existing.get("documents") or [])
        metadatas = list(existing.get("metadatas") or [])

        if len(documents) != len(ids):
            documents = [""] * len(ids)
        if len(metadatas) != len(ids):
            metadatas = [{"document_id": document_id, "block_id": item_id} for item_id in ids]
        return {"ids": ids, "documents": documents, "metadatas": metadatas}

    def _rollback_blocks(self, block_collection, old_snapshot: Dict[str, Any], new_ids: list[str]) -> None:
        if block_collection is None:
            return
        try:
            if new_ids:
                block_collection.delete(ids=new_ids)
            if old_snapshot.get("ids"):
                block_collection.add(
                    documents=old_snapshot.get("documents") or [],
                    metadatas=old_snapshot.get("metadatas") or [],
                    ids=old_snapshot.get("ids") or [],
                )
        except Exception:
            pass
