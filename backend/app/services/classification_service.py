import asyncio
import json
import threading
from typing import Dict, List

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

    def _build_pending_sync_result(self) -> Dict:
        return {
            "classification_id": "system.pending_sync",
            "classification_label": "待本地索引同步",
            "classification_path": ["待同步", "待本地索引同步"],
            "classification_score": 0.0,
            "classification_source": "pending_sync",
            "classification_candidates": [],
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

    def classify(self, document_id: str) -> Dict:
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
                result = self._build_pending_sync_result()
                self._save_taxonomy_result(document_id, result)
                return self._serialize_taxonomy_assignment(doc_info, result)

            if not str(content or "").strip():
                semantic_summary = self._load_lightrag_semantic_summary(document_id, doc_info)
                if semantic_summary:
                    content = semantic_summary

            if self._requires_local_sync(doc_info, content_record, semantic_summary):
                result = self._build_pending_sync_result()
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
            self._schedule_topic_tree_update(document_id)
        except Exception as exc:
            raise AppServiceError(1005, f"文档 taxonomy 分类失败: {exc}")

        return self._serialize_taxonomy_assignment(doc_info, result)

    def reclassify(self, document_id: str) -> Dict:
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
                result = self._build_pending_sync_result()
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
                result = self._build_pending_sync_result()
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
            self._schedule_topic_tree_update(document_id)
        except Exception as exc:
            raise AppServiceError(1005, f"文档 taxonomy 分类失败: {exc}")

        payload = self._serialize_taxonomy_assignment(doc_info, result)
        payload["old_classification"] = old_classification
        payload["new_classification"] = result.get("classification_label")
        return payload

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
        return self.topic_tree_service.get_documents_by_topic(category)

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
            "classification_label": classification_label,
            "classification_path": classification_path,
            "classification_score": float(result.get("classification_score", 0.0) or 0.0),
            "classification_candidates": list(result.get("classification_candidates") or []),
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
        update_document_info(
            document_id,
            {
                "classification_result": result.get("classification_label"),
                "classification_id": result.get("classification_id"),
                "classification_path": json.dumps(
                    result.get("classification_path") or [],
                    ensure_ascii=False,
                ),
                "classification_score": float(result.get("classification_score", 0.0) or 0.0),
                "classification_source": result.get("classification_source"),
                "classification_candidates": json.dumps(
                    list(result.get("classification_candidates") or []),
                    ensure_ascii=False,
                ),
            },
        )

    def _schedule_topic_tree_update(self, document_id: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            thread = threading.Thread(
                target=lambda: asyncio.run(self._async_update_topic_tree(document_id)),
                daemon=True,
            )
            thread.start()
            return
        asyncio.create_task(self._async_update_topic_tree(document_id))

    async def _async_update_topic_tree(self, document_id: str) -> None:
        try:
            await asyncio.to_thread(self.topic_tree_service.build_topic_tree, True)
        except Exception as exc:
            from app.core.logger import logger

            logger.opt(exception=exc).error(
                "async_topic_tree_update_failed document_id={}",
                document_id,
            )

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
