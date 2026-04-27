import asyncio
import json
import threading
from typing import Dict, List

from app.core.logger import logger
from app.domain.classification_contract import (
    SPECIAL_ERROR_LABEL,
    normalize_classification_label,
)
from app.domain.taxonomy.internet_enterprise_taxonomy import get_all_labels
from app.infra.file_utils import create_classification_directory
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.classification_table_repository import ClassificationTableRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.services.document_label_resolver import (
    is_error_document,
    load_source_text,
    resolve_document_label,
)
from app.services.errors import AppServiceError
from app.services.lightrag_semantic_service import LightRAGSemanticService
from app.services.taxonomy_classifier import TaxonomyClassifier
from app.services.topic_tree_service import TopicTreeService
from config import DATA_DIR
from utils.smart_retrieval import generate_classification_table


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _document_content_repository() -> DocumentContentRepository:
    return DocumentContentRepository(data_dir=DATA_DIR)


def _classification_table_repository() -> ClassificationTableRepository:
    return ClassificationTableRepository(data_dir=DATA_DIR)


def get_document_info(document_id: str):
    return _document_repository().get(document_id)


def get_document_content_record(document_id: str):
    return _document_content_repository().get(document_id)


def update_document_info(document_id: str, updated_info: Dict) -> bool:
    return _document_repository().update(document_id, updated_info)


def save_classification_table_record(table_payload: Dict, table_id: str | None = None):
    return _classification_table_repository().save(table_payload, table_id)


def get_classification_table_record(table_id: str):
    return _classification_table_repository().get(table_id)


def list_classification_table_records(limit: int = 50):
    return _classification_table_repository().list(limit)


def get_all_documents():
    return _document_repository().list_all()


class TopicTreeRefreshScheduler:
    def __init__(self, service_factory=TopicTreeService):
        self.service_factory = service_factory
        self._lock = threading.Lock()
        self._running = False
        self._pending = False
        self._last_source = None

    def request_refresh(self, source: str) -> Dict:
        normalized_source = str(source or "unknown")
        with self._lock:
            self._last_source = normalized_source
            if self._running:
                self._pending = True
                return {
                    "scheduled": False,
                    "coalesced": True,
                    "source": normalized_source,
                }

            self._running = True
            self._pending = False

        worker = threading.Thread(
            target=self._run,
            name="topic-tree-refresh",
            daemon=True,
        )
        worker.start()
        return {
            "scheduled": True,
            "coalesced": False,
            "source": normalized_source,
        }

    def _run(self) -> None:
        while True:
            source = self._last_source
            try:
                self.service_factory().build_topic_tree(force_rebuild=True)
            except Exception as exc:
                from app.core.logger import logger

                logger.opt(exception=exc).error(
                    "async_topic_tree_update_failed source={}",
                    source,
                )

            with self._lock:
                if self._pending:
                    self._pending = False
                    continue
                self._running = False
                return


_topic_tree_refresh_scheduler = TopicTreeRefreshScheduler()


class ClassificationService:
    def __init__(self):
        self.topic_tree_service = TopicTreeService()
        self.semantic_service = LightRAGSemanticService()

    @staticmethod
    def _requires_local_sync(
        doc_info: Dict,
        content_record: Dict | None = None,
        semantic_summary: str = "",
    ) -> bool:
        content_record = content_record or {}
        ingest_status = str(doc_info.get("ingest_status") or "").lower()
        extraction_status = str(
            content_record.get("extraction_status")
            or doc_info.get("extraction_status")
            or ""
        ).lower()
        has_local_content = bool(
            str(content_record.get("full_content") or "").strip()
            or str(content_record.get("preview_content") or "").strip()
            or str(doc_info.get("full_content") or "").strip()
            or str(doc_info.get("preview_content") or "").strip()
            or str(doc_info.get("content") or "").strip()
            or str(semantic_summary or "").strip()
        )
        has_lightrag_identity = bool(doc_info.get("lightrag_doc_id") or doc_info.get("lightrag_track_id"))

        if has_local_content:
            return False

        if ingest_status == "local_only":
            return True

        if has_lightrag_identity and extraction_status in {"", "pending", "processing"}:
            return True

        return False

    def _build_pending_local_content_result(self) -> Dict:
        return {
            "classification_id": None,
            "classification_label": None,
            "classification_path": [],
            "classification_score": 0.0,
            "classification_source": "pending_local_content",
            "classification_candidates": [],
            "classification_review_status": "none",
            "classification_issue_code": "pending_local_content",
        }

    @classmethod
    def _should_short_circuit_pending_sync(
        cls,
        doc_info: Dict,
        content_record: Dict | None = None,
        content: str = "",
    ) -> bool:
        if str(content or "").strip():
            return False
        return cls._requires_local_sync(doc_info, content_record, semantic_summary="")

    def classify(self, document_id: str, *, schedule_topic_tree_update: bool = True) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        if is_error_document(document_id, doc_info):
            self._persist_error_label(document_id)
            return self._serialize_error_assignment(doc_info)

        try:
            content_record = get_document_content_record(document_id) or {}
            content = self._load_document_content(document_id, doc_info)
            semantic_summary = ""
            if self._should_short_circuit_pending_sync(doc_info, content_record, content):
                result = self._build_pending_local_content_result()
                self._save_taxonomy_result(document_id, result)
                return self._serialize_taxonomy_assignment(doc_info, result)

            if not str(content or "").strip():
                semantic_summary = self._load_lightrag_semantic_summary(document_id, doc_info)
                if semantic_summary:
                    content = semantic_summary

            if self._requires_local_sync(doc_info, content_record, semantic_summary):
                result = self._build_pending_local_content_result()
                self._save_taxonomy_result(document_id, result)
                return self._serialize_taxonomy_assignment(doc_info, result)

            taxonomy_classifier = TaxonomyClassifier()
            result = self._run_coroutine(
                taxonomy_classifier.classify(
                    document_id,
                    content,
                    doc_info.get("filename", ""),
                    doc_info.get("file_type", ""),
                )
            )
            self._save_taxonomy_result(document_id, result)
            self._sync_classified_storage_best_effort(document_id)
            if schedule_topic_tree_update and result.get("classification_label"):
                self._schedule_topic_tree_update(document_id)
        except Exception as exc:
            raise AppServiceError(1005, f"文档 taxonomy 分类失败: {exc}")

        return self._serialize_taxonomy_assignment(doc_info, result)

    def reclassify(self, document_id: str, *, schedule_topic_tree_update: bool = True) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        old_classification = doc_info.get("classification_result")
        if is_error_document(document_id, doc_info):
            self._persist_error_label(document_id)
            payload = self._serialize_error_assignment(doc_info)
            payload["old_classification"] = old_classification
            payload["new_classification"] = SPECIAL_ERROR_LABEL
            return payload

        try:
            content_record = get_document_content_record(document_id) or {}
            content = self._load_document_content(document_id, doc_info)
            semantic_summary = ""
            if self._should_short_circuit_pending_sync(doc_info, content_record, content):
                result = self._build_pending_local_content_result()
                self._save_taxonomy_result(document_id, result)
                payload = self._serialize_taxonomy_assignment(doc_info, result)
                payload["old_classification"] = old_classification
                payload["new_classification"] = result.get("classification_label")
                return payload

            if not str(content or "").strip():
                semantic_summary = self._load_lightrag_semantic_summary(document_id, doc_info)
                if semantic_summary:
                    content = semantic_summary

            if self._requires_local_sync(doc_info, content_record, semantic_summary):
                result = self._build_pending_local_content_result()
                self._save_taxonomy_result(document_id, result)
                payload = self._serialize_taxonomy_assignment(doc_info, result)
                payload["old_classification"] = old_classification
                payload["new_classification"] = result.get("classification_label")
                return payload

            taxonomy_classifier = TaxonomyClassifier()
            result = self._run_coroutine(
                taxonomy_classifier.classify(
                    document_id,
                    content,
                    doc_info.get("filename", ""),
                    doc_info.get("file_type", ""),
                )
            )
            self._save_taxonomy_result(document_id, result)
            self._sync_classified_storage_best_effort(document_id)
            if schedule_topic_tree_update and result.get("classification_label"):
                self._schedule_topic_tree_update(document_id)
        except Exception as exc:
            raise AppServiceError(1005, f"文档 taxonomy 分类失败: {exc}")

        payload = self._serialize_taxonomy_assignment(doc_info, result)
        payload["old_classification"] = old_classification
        payload["new_classification"] = result.get("classification_label")
        return payload

    def batch_reclassify(self, filters: Dict) -> Dict:
        documents = list(get_all_documents())
        selected = self._select_documents_for_reclassification(documents, filters)
        items = []
        success_count = 0
        failed_count = 0

        for doc in selected:
            document_id = doc.get("id") or doc.get("document_id")
            if not document_id:
                continue
            try:
                old_snapshot = {
                    "classification_result": doc.get("classification_result"),
                    "classification_path": doc.get("classification_path"),
                    "classification_issue_code": doc.get("classification_issue_code"),
                    "taxonomy_version": doc.get("taxonomy_version"),
                }
                payload = self.reclassify(document_id, schedule_topic_tree_update=False)
                success_count += 1
                items.append(
                    {
                        "document_id": document_id,
                        "status": "success",
                        "old": old_snapshot,
                        "new": payload,
                    }
                )
            except Exception as exc:
                failed_count += 1
                items.append(
                    {
                        "document_id": document_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        return {
            "total": len(selected),
            "success_count": success_count,
            "failed_count": failed_count,
            "items": items,
        }

    @staticmethod
    def _select_documents_for_reclassification(documents: List[Dict], filters: Dict) -> List[Dict]:
        filters = filters or {}
        explicit_ids = {str(item) for item in filters.get("document_ids") or [] if str(item).strip()}
        issue_codes = {str(item) for item in filters.get("issue_codes") or [] if str(item).strip()}
        taxonomy_versions = {str(item) for item in filters.get("taxonomy_versions") or [] if str(item).strip()}
        file_types = {
            str(item).lower()
            for item in filters.get("file_types") or []
            if str(item).strip()
        }
        limit = max(int(filters.get("limit") or 100), 0)

        selected = []
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            document_id = str(doc.get("id") or doc.get("document_id") or "")
            if explicit_ids and document_id not in explicit_ids:
                continue
            if issue_codes and str(doc.get("classification_issue_code") or "") not in issue_codes:
                continue
            if taxonomy_versions and str(doc.get("taxonomy_version") or "") not in taxonomy_versions:
                continue
            if file_types and str(doc.get("file_type") or "").lower() not in file_types:
                continue
            selected.append(doc)
            if limit and len(selected) >= limit:
                break
        return selected

    def clear(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        old_classification = doc_info.get("classification_result")
        if not old_classification:
            return {"document_id": document_id, "message": "文档本身未分类，无需清除"}

        update_document_info(
            document_id,
            {
                "classification_result": None,
                "topic_node_id": None,
                "topic_label": None,
                "topic_path": [],
                "topic_parent_label": None,
                "topic_tree_generated_at": None,
            },
        )
        return {"document_id": document_id, "old_classification": old_classification}

    def get_categories(self) -> Dict:
        labels = get_all_labels()
        if labels:
            return [
                {
                    "id": label.get("id"),
                    "label": label.get("label"),
                    "path": list(label.get("path") or []),
                    "domain": (label.get("path") or [""])[0],
                }
                for label in labels
            ]
        return self.topic_tree_service.get_category_overview()

    def get_documents_by_category(self, category: str) -> Dict:
        normalized = str(category or "").strip()
        if not normalized:
            return {
                "category": "",
                "topic_id": None,
                "topic_path": [],
                "total": 0,
                "documents": [],
            }

        documents = []
        for doc in get_all_documents() or []:
            if not isinstance(doc, dict):
                continue
            classification_id = str(doc.get("classification_id") or "").strip()
            classification_result = str(doc.get("classification_result") or "").strip()
            if normalized not in {classification_id, classification_result}:
                continue

            raw_path = doc.get("classification_path")
            if isinstance(raw_path, str):
                try:
                    raw_path = json.loads(raw_path)
                except json.JSONDecodeError:
                    raw_path = []

            documents.append(
                {
                    "id": doc.get("id"),
                    "document_id": doc.get("id"),
                    "filename": doc.get("filename", ""),
                    "file_type": doc.get("file_type", ""),
                    "classification_result": doc.get("classification_result"),
                    "topic_path": list(raw_path or []),
                    "created_at_iso": doc.get("created_at_iso"),
                    "excerpt": doc.get("excerpt", "") or doc.get("preview_content", "") or "",
                    "keywords": [],
                }
            )

        documents.sort(
            key=lambda item: (item.get("created_at_iso") or "", item.get("filename") or ""),
            reverse=True,
        )
        category_label = documents[0]["classification_result"] if documents else normalized
        category_path = documents[0]["topic_path"] if documents else []
        return {
            "category": category_label,
            "topic_id": normalized,
            "topic_path": category_path,
            "total": len(documents),
            "documents": documents,
        }

    def batch_classify_ready_documents(
        self,
        *,
        limit: int = 100,
        include_needs_review: bool = True,
        force: bool = False,
    ) -> Dict:
        normalized_limit = max(int(limit or 0), 0)
        candidates = []
        for doc in get_all_documents() or []:
            if not isinstance(doc, dict) or not doc.get("id"):
                continue
            local_index_status = str(doc.get("local_index_status") or "").lower()
            if local_index_status != "ready":
                continue
            has_classification = bool(str(doc.get("classification_result") or "").strip())
            issue_code = str(doc.get("classification_issue_code") or "").strip()
            if force or not has_classification or (
                include_needs_review and issue_code in {"no_match", "pending_local_content"}
            ):
                candidates.append(str(doc["id"]))
            if normalized_limit > 0 and len(candidates) >= normalized_limit:
                break

        results = []
        classified = 0
        needs_review = 0
        failed = 0
        should_refresh_topic_tree = False
        for document_id in candidates:
            try:
                result = (
                    self.reclassify(document_id, schedule_topic_tree_update=False)
                    if force
                    else self.classify(document_id, schedule_topic_tree_update=False)
                )
                issue_code = result.get("classification_issue_code")
                label = result.get("classification_label") or result.get("topic_label")
                if label:
                    classified += 1
                    should_refresh_topic_tree = True
                if issue_code:
                    needs_review += 1
                results.append(
                    {
                        "document_id": document_id,
                        "classification_label": label,
                        "classification_issue_code": issue_code,
                        "classification_source": result.get("classification_source"),
                    }
                )
            except Exception as exc:
                failed += 1
                results.append(
                    {
                        "document_id": document_id,
                        "error": str(exc),
                        "classification_issue_code": "failed",
                    }
                )

        if should_refresh_topic_tree:
            self._schedule_topic_tree_update("batch")

        return {
            "results": results,
            "total": len(candidates),
            "classified": classified,
            "needs_review": needs_review,
            "failed": failed,
        }

    def create_folder(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        try:
            assignment = self.topic_tree_service.classify_document(document_id, force_rebuild=False)
        except Exception as exc:
            raise AppServiceError(1006, f"文档尚未完成主题归类: {exc}")

        success, target_path = create_classification_directory(doc_info, assignment.get("topic_path") or [assignment.get("topic_label")])
        if not success:
            raise AppServiceError(1005, "分类目录创建失败")

        if target_path:
            update_document_info(document_id, {"filepath": target_path})
        return {"document_id": document_id, "target_path": target_path}

    def build_multi_level_tree(self, force_rebuild: bool) -> Dict:
        tree = self.topic_tree_service.build_topic_tree(force_rebuild=force_rebuild)
        return self.topic_tree_service.get_legacy_tree_payload() if tree else {"generated_at": "", "total_documents": 0, "tree": {}}

    def get_multi_level_tree(self) -> Dict:
        return self.topic_tree_service.get_legacy_tree_payload()

    def build_topic_tree(self, force_rebuild: bool = False) -> Dict:
        return self.topic_tree_service.build_topic_tree(force_rebuild=force_rebuild)

    def get_topic_tree(self) -> Dict:
        return self.topic_tree_service.get_topic_tree()

    def get_document_multi_level_info(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        if is_error_document(document_id, doc_info):
            return self._serialize_error_assignment(doc_info)
        try:
            assignment = self.topic_tree_service.classify_document(document_id, force_rebuild=False)
        except Exception as exc:
            raise AppServiceError(1005, f"文档主题归类失败: {exc}")
        return self._serialize_assignment(doc_info, assignment)

    def generate_classification_table(self, query: str, results: List[Dict], persist: bool = True) -> Dict:
        if not query or not query.strip():
            raise AppServiceError(3002, "查询关键词不能为空")
        if not results:
            raise AppServiceError(3002, "检索结果为空，无法生成分类表")

        hydrated_results = []
        doc_cache: Dict[str, Dict] = {}
        for item in results:
            doc_id = item.get("document_id")
            doc_info = doc_cache.get(doc_id)
            if doc_info is None and doc_id:
                doc_info = get_document_info(doc_id) or {}
                doc_cache[doc_id] = doc_info

            hydrated_results.append(
                {
                    **item,
                    "classification_result": (doc_info or {}).get("classification_result"),
                    "document_category": (doc_info or {}).get("classification_result"),
                    "created_at_iso": (doc_info or {}).get("created_at_iso"),
                    "best_excerpt": item.get("best_excerpt") or item.get("content_snippet") or "",
                }
            )

        table = generate_classification_table(query, hydrated_results)
        if persist:
            table_id = save_classification_table_record(table)
            table["id"] = table_id
        return table

    def list_classification_tables(self, limit: int = 50) -> Dict:
        tables = list_classification_table_records(limit=limit)
        return {"items": tables, "total": len(tables)}

    def get_classification_table(self, table_id: str) -> Dict:
        table = get_classification_table_record(table_id)
        if not table:
            raise AppServiceError(1001, f"分类表ID: {table_id}")
        return table

    @staticmethod
    def _serialize_assignment(doc_info: Dict, assignment: Dict) -> Dict:
        topic_path = list(assignment.get("topic_path") or [])
        topic_label = assignment.get("topic_label") or (topic_path[-1] if topic_path else None)
        return {
            "document_id": doc_info.get("id"),
            "filename": doc_info.get("filename", ""),
            "categories": topic_path or ([topic_label] if topic_label else []),
            "confidence": float(assignment.get("confidence", 1.0) or 1.0),
            "suggested_folders": ["/".join(topic_path)] if topic_path else [],
            "topic_id": assignment.get("topic_id"),
            "topic_label": topic_label,
            "topic_path": topic_path,
            "classification_source": "topic_tree",
        }

    @staticmethod
    def _serialize_taxonomy_assignment(doc_info: Dict, result: Dict) -> Dict:
        classification_path = list(result.get("classification_path") or [])
        classification_label = result.get("classification_label")
        return {
            "document_id": doc_info.get("id"),
            "filename": doc_info.get("filename", ""),
            "categories": classification_path or ([classification_label] if classification_label else []),
            "confidence": float(result.get("classification_score", 0.0) or 0.0),
            "suggested_folders": ["/".join(classification_path)] if classification_path else [],
            "topic_id": result.get("classification_id"),
            "topic_label": classification_label,
            "topic_path": classification_path,
            "classification_source": result.get("classification_source", "taxonomy"),
            "classification_id": result.get("classification_id"),
            "classification_leaf_id": result.get("classification_leaf_id") or result.get("classification_id"),
            "classification_domain": result.get("classification_domain"),
            "classification_label": classification_label,
            "classification_path": classification_path,
            "classification_score": float(result.get("classification_score", 0.0) or 0.0),
            "classification_confidence": float(
                result.get("classification_confidence", result.get("classification_score", 0.0)) or 0.0
            ),
            "classification_candidates": list(result.get("classification_candidates") or []),
            "classification_review_status": result.get("classification_review_status", "none"),
            "classification_issue_code": result.get("classification_issue_code"),
            "taxonomy_version": result.get("taxonomy_version", "taxonomy_v1"),
        }

    @staticmethod
    def _load_document_content(document_id: str, doc_info: Dict) -> str:
        content_record = get_document_content_record(document_id) or {}
        content = (
            content_record.get("full_content")
            or content_record.get("preview_content")
            or doc_info.get("full_content")
            or doc_info.get("preview_content")
            or doc_info.get("content")
            or doc_info.get("excerpt")
            or doc_info.get("summary_source")
            or ""
        )
        return str(content or "")[:2000]

    def _load_lightrag_semantic_summary(self, document_id: str, doc_info: Dict) -> str:
        del document_id
        has_lightrag_identity = bool(doc_info.get("lightrag_doc_id") or doc_info.get("lightrag_track_id"))
        if not has_lightrag_identity:
            return ""

        try:
            snapshot = self._run_coroutine(
                self.semantic_service.get_document_semantic_snapshot(doc_info, top_k=12)
            )
        except Exception:
            return ""

        return str((snapshot or {}).get("summary_text") or "")[:2000]

    @staticmethod
    def _run_coroutine(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result_holder: Dict[str, object] = {}
        error_holder: Dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result_holder["value"] = asyncio.run(coro)
            except BaseException as exc:  # pragma: no cover - defensive bridge
                error_holder["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if error_holder:
            raise error_holder["error"]
        return result_holder.get("value")

    def _save_taxonomy_result(self, document_id: str, result: Dict) -> None:
        classification_path = list(result.get("classification_path") or [])
        classification_candidates = list(result.get("classification_candidates") or [])
        update_document_info(
            document_id,
            {
                "classification_result": result.get("classification_label"),
                "classification_id": result.get("classification_id"),
                "classification_leaf_id": result.get("classification_leaf_id") or result.get("classification_id"),
                "classification_path": json.dumps(classification_path, ensure_ascii=False),
                "classification_domain": result.get("classification_domain"),
                "classification_score": float(result.get("classification_score", 0.0) or 0.0),
                "classification_confidence": float(
                    result.get("classification_confidence", result.get("classification_score", 0.0)) or 0.0
                ),
                "classification_source": (
                    result.get("classification_source")
                    if result.get("classification_label")
                    else None
                ),
                "classification_candidates": json.dumps(classification_candidates, ensure_ascii=False),
                "classification_review_status": result.get("classification_review_status", "none"),
                "classification_issue_code": result.get("classification_issue_code"),
                "taxonomy_version": result.get("taxonomy_version", "taxonomy_v1"),
            },
        )

    def sync_classified_storage(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        filepath = str(doc_info.get("filepath") or "").strip()
        if "/classified_docs/" not in filepath.replace("\\", "/"):
            return {
                "document_id": document_id,
                "synced": False,
                "moved": False,
                "reason": "not_in_classified_docs",
                "filepath": filepath,
            }

        classification_path = self._parse_classification_path(doc_info.get("classification_path"))
        if not classification_path:
            return {
                "document_id": document_id,
                "synced": False,
                "moved": False,
                "reason": "missing_classification_path",
                "filepath": filepath,
            }

        success, target_path = create_classification_directory(doc_info, classification_path)
        if not success or not target_path:
            return {
                "document_id": document_id,
                "synced": False,
                "moved": False,
                "reason": "move_failed",
                "filepath": filepath,
            }

        moved = str(target_path) != filepath
        if moved:
            update_document_info(document_id, {"filepath": target_path})

        return {
            "document_id": document_id,
            "synced": True,
            "moved": moved,
            "filepath": target_path,
            "classification_path": classification_path,
        }

    def _sync_classified_storage_best_effort(self, document_id: str) -> None:
        try:
            self.sync_classified_storage(document_id)
        except Exception as exc:
            logger.opt(exception=exc).warning(
                "sync_classified_storage_failed document_id={}",
                document_id,
            )

    @staticmethod
    def _parse_classification_path(raw_path: object) -> List[str]:
        if isinstance(raw_path, list):
            return [str(item).strip() for item in raw_path if str(item or "").strip()]
        if isinstance(raw_path, str):
            text = raw_path.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item or "").strip()]
            return [segment.strip() for segment in text.split("/") if segment.strip()]
        return []

    def _schedule_topic_tree_update(self, document_id: str) -> None:
        _topic_tree_refresh_scheduler.request_refresh(document_id)

    async def classify_document(self, document_id: str) -> str:
        """
        双路分类 + LLM 仲裁

        路径 A: 向量聚类（现有逻辑）
        路径 B: LLM zero-shot 分类（新）
        仲裁: LLM 比较两路结果，选择最合适的

        Args:
            document_id: 文档 ID

        Returns:
            最终分类标签
        """
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        assignment_a = None
        try:
            source_text = load_source_text(document_id, doc_info)
            if is_error_document(document_id, doc_info):
                self._persist_error_label(document_id)
                return SPECIAL_ERROR_LABEL

            # 路径 A: 向量聚类（现有逻辑）
            assignment_a = self.topic_tree_service.classify_document(document_id, force_rebuild=False)
            label_a = normalize_classification_label(assignment_a.get("topic_label", ""))

            # 路径 B: LLM zero-shot 分类
            from app.domain.llm.gateway import LLMGateway
            llm_gateway = LLMGateway()
            label_result = await resolve_document_label(document_id, doc_info, llm_gateway=llm_gateway)
            label_b = normalize_classification_label(label_result.get("label", ""))
            if label_result.get("is_error") or label_b == SPECIAL_ERROR_LABEL:
                self._persist_error_label(document_id)
                return SPECIAL_ERROR_LABEL
            source_text = label_result.get("source_text") or source_text

            confidence = 1.0

            if label_a and label_b and label_a != label_b:
                arbitration = await llm_gateway.arbitrate_labels(source_text[:500], label_a, label_b)
                final_label = normalize_classification_label(arbitration.get("final_label", "")) or label_a
                confidence = arbitration.get("confidence", 0.5)
            else:
                final_label = label_a or label_b or SPECIAL_ERROR_LABEL

            method = "dual-path LLM arbitration" if label_a and label_b and label_a != label_b else "classification_contract"

            update_document_info(document_id, {
                "classification_result": final_label,
                "classification_confidence": confidence,
                "classification_method": method,
            })

            return final_label

        except Exception:
            # Fallback：使用路径 A 的结果
            try:
                assignment = assignment_a if assignment_a is not None else self.topic_tree_service.classify_document(document_id, force_rebuild=False)
                fallback_label = normalize_classification_label(assignment.get("topic_label", "")) or SPECIAL_ERROR_LABEL
                if fallback_label == SPECIAL_ERROR_LABEL:
                    self._persist_error_label(document_id)
                else:
                    update_document_info(
                        document_id,
                        {
                            "classification_result": fallback_label,
                            "classification_confidence": float(assignment.get("confidence", 1.0) or 1.0),
                            "classification_method": "topic_tree_fallback",
                        },
                    )
                return fallback_label
            except Exception:
                self._persist_error_label(document_id)
                return SPECIAL_ERROR_LABEL

    @staticmethod
    def _serialize_error_assignment(doc_info: Dict) -> Dict:
        error_topic_path = ["异常文档", SPECIAL_ERROR_LABEL]
        return {
            "document_id": doc_info.get("id"),
            "filename": doc_info.get("filename", ""),
            "categories": error_topic_path,
            "confidence": 1.0,
            "suggested_folders": ["异常文档/Error"],
            "topic_id": None,
            "topic_label": SPECIAL_ERROR_LABEL,
            "topic_path": error_topic_path,
            "classification_source": "content_error_fallback",
        }

    @staticmethod
    def _persist_error_label(document_id: str) -> None:
        update_document_info(
            document_id,
            {
                "classification_result": SPECIAL_ERROR_LABEL,
                "classification_confidence": 1.0,
                "classification_method": "content_error_fallback",
                "topic_node_id": None,
                "topic_label": None,
                "topic_path": [],
                "topic_parent_label": None,
                "topic_tree_generated_at": None,
            },
        )
