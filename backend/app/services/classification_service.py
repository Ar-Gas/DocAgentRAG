from typing import Dict, List

from app.infra.file_utils import create_classification_directory
from app.infra.repositories.classification_table_repository import ClassificationTableRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.services.errors import AppServiceError
from app.services.topic_tree_service import TopicTreeService
from config import DATA_DIR
from utils.smart_retrieval import generate_classification_table


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _classification_table_repository() -> ClassificationTableRepository:
    return ClassificationTableRepository(data_dir=DATA_DIR)


def get_document_info(document_id: str):
    return _document_repository().get(document_id)


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

    def classify(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        try:
            assignment = self.topic_tree_service.classify_document(document_id, force_rebuild=True)
        except Exception as exc:
            raise AppServiceError(1005, f"文档主题归类失败: {exc}")

        return self._serialize_assignment(doc_info, assignment)

    def reclassify(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        old_classification = doc_info.get("classification_result")
        try:
            assignment = self.topic_tree_service.classify_document(document_id, force_rebuild=True)
        except Exception as exc:
            raise AppServiceError(1005, f"文档主题归类失败: {exc}")

        payload = self._serialize_assignment(doc_info, assignment)
        payload["old_classification"] = old_classification
        payload["new_classification"] = assignment.get("topic_label")
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
