import os
import re
import shutil
import asyncio
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.core.logger import logger
from app.infra.lightrag_client import LightRAGClient
from app.infra.file_utils import enrich_document_file_state as _enrich_document_file_state
from app.infra.repositories.document_artifact_repository import DocumentArtifactRepository
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.infra.vector_store import get_block_collection
from app.services.document_vector_index_service import DocumentVectorIndexService
from app.services.errors import AppServiceError
from app.services.extraction_service import ExtractionService
from app.services.indexing_service import IndexingService
from app.services.local_embedding_runtime import LocalEmbeddingRuntime
from config import ALLOWED_EXTENSIONS, BASE_DIR, DATA_DIR, DOC_DIR, EXTENSION_TO_DIR, MAX_FILE_SIZE
from utils.retriever import get_query_parser
from utils.search_cache import get_search_cache


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
    lightrag_track_id: Optional[str] = None,
    lightrag_doc_id: Optional[str] = None,
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
        data_dir: Path = DATA_DIR,
        doc_dir: Path = DOC_DIR,
        lightrag_client=None,
        local_embedding_runtime=None,
        enqueue_background: bool = True,
    ):
        self.document_repository = document_repository
        self.data_dir = Path(data_dir)
        self.doc_dir = Path(doc_dir)
        self.lightrag_client = lightrag_client or LightRAGClient()
        self.local_embedding_runtime = local_embedding_runtime or LocalEmbeddingRuntime()
        self.enqueue_background = enqueue_background
        self.extraction_service = ExtractionService()
        self.indexing_service = IndexingService()
        self._batch_import_task = None
        self._batch_import_status = self._initial_batch_import_status()

    def _document_repository(self) -> DocumentRepository:
        return self.document_repository or _document_repository()

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
        lightrag_track_id: Optional[str] = None,
        lightrag_doc_id: Optional[str] = None,
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
        return _enrich_document_file_state(
            doc_info,
            base_dir=BASE_DIR,
            doc_dir=self.doc_dir,
            get_document_info=self._get_document_info,
            update_document_info=self._update_document_info,
            persist=True,
        )

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

    def _sync_processing_ingest_status(self, doc_info: Dict) -> Dict:
        if not isinstance(doc_info, dict):
            return doc_info

        ingest_status = str(doc_info.get("ingest_status") or "").lower()
        track_id = str(doc_info.get("lightrag_track_id") or "").strip()
        if ingest_status not in {"processing", "failed"} or not track_id:
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
            ingest_error = next(
                (
                    str(item.get("error_msg") or "").strip()
                    for item in documents
                    if isinstance(item, dict) and str(item.get("error_msg") or "").strip()
                ),
                "LightRAG processing failed",
            )
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="failed",
                ingest_error=ingest_error,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        in_progress_statuses = {"pending", "processing", "preprocessed"}
        if statuses and statuses.issubset({"processed"}):
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="ready",
                ingest_error=None,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=now,
            )
            return self._get_document_info(doc_info["id"]) or doc_info

        if statuses & in_progress_statuses:
            self._update_ingest_status(
                doc_info["id"],
                ingest_status="processing",
                ingest_error=None,
                lightrag_doc_id=remote_doc.get("id"),
                last_status_sync_at=now,
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
            "ingest_status": "queued",
            "ingest_error": None,
            "lightrag_track_id": None,
            "lightrag_doc_id": None,
            "last_status_sync_at": None,
        }
        if not self._document_repository().upsert(doc_info):
            if file_path.exists():
                os.remove(file_path)
            raise AppServiceError(1002, "文档元数据保存失败")
        logger.info("document_metadata_persisted document_id={} filename={}", document_id, safe_name)

        if self.enqueue_background:
            self._enqueue_ingest(document_id)

        return self._hydrate_document(doc_info)

    def _enqueue_ingest(self, document_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.process_pending_ingest(document_id))
        except RuntimeError:
            logger.warning("no_running_loop_for_ingest_enqueue document_id={}", document_id)

    async def process_pending_ingest(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        if (doc_info.get("ingest_status") or "") not in {"queued", "failed", "processing", "local_only"}:
            return doc_info

        self._update_ingest_status(
            document_id,
            ingest_status="processing",
            ingest_error=None,
            last_status_sync_at=datetime.now().isoformat(),
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
                await self.lightrag_client.reprocess_failed_documents()
                self._update_ingest_status(
                    document_id,
                    ingest_status="processing",
                    ingest_error=None,
                    lightrag_track_id=track_id,
                    last_status_sync_at=datetime.now().isoformat(),
                )
                try:
                    get_search_cache().invalidate_all()
                except Exception:
                    pass
                return self._get_document_info(document_id) or processing_doc
            if status in {"failed", "error"}:
                raise RuntimeError(result.get("message") or "LightRAG upload failed")
            self._update_ingest_status(
                document_id,
                ingest_status="processing",
                ingest_error=None,
                lightrag_track_id=track_id,
                last_status_sync_at=datetime.now().isoformat(),
            )
            try:
                get_search_cache().invalidate_all()
            except Exception:
                pass
            return self.get_document(document_id)
        except Exception as exc:
            error_message = str(exc)
            logger.warning("document_ingest_failed document_id={} error={}", document_id, error_message)
            self._update_ingest_status(
                document_id,
                ingest_status="failed",
                ingest_error=error_message,
                last_status_sync_at=datetime.now().isoformat(),
            )
            return self.get_document(document_id)

    def _list_batch_import_candidates(self, *, limit: int, include_failed: bool) -> List[Dict]:
        statuses = {"local_only"}
        if include_failed:
            statuses.add("failed")

        documents = [
            item
            for item in (self._document_repository().list_all() or [])
            if isinstance(item, dict) and (item.get("ingest_status") or "").lower() in statuses
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

    def get_document_payload(self, document_id: str) -> Dict:
        doc_info = self.get_document(document_id)
        content_record = get_document_content_record(document_id) or {}
        segments = list_document_segments(document_id)
        artifacts = list_document_artifacts(document_id)
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
        content_record = get_document_content_record(document_id) or {}
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

    def _build_reader_blocks(self, document_id: str, content_record: Dict) -> List[Dict]:
        artifact = get_document_artifact(document_id, "reader_blocks") or {}
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

        segments = list_document_segments(document_id)
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
