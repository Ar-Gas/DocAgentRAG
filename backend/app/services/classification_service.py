from typing import Dict, List

from app.infra.repositories.classification_table_repository import ClassificationTableRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.vector_store import get_chroma_collection
from app.services.document_vector_index_service import DocumentVectorIndexService
from app.services.errors import AppServiceError
from app.services.legacy_classification_tree_bridge import update_classification_tree_after_reclassify as _bridge_reclassify
from app.services.topic_tree_service import TopicTreeService
from config import BASE_DIR, DATA_DIR
from utils.classifier import classify_document, create_classification_directory
from utils.smart_retrieval import generate_classification_table
from utils.multi_level_classifier import (
    build_and_save_classification_tree,
    get_classification_tree,
    get_multi_level_classifier,
)


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _classification_table_repository() -> ClassificationTableRepository:
    return ClassificationTableRepository(data_dir=DATA_DIR)


def _vector_index_service() -> DocumentVectorIndexService:
    return DocumentVectorIndexService(document_repository=_document_repository())


def get_document_info(document_id: str):
    return _document_repository().get(document_id)


def get_all_documents():
    return _document_repository().list_all()


def get_documents_by_classification(classification: str):
    return _document_repository().list_by_classification(classification)


def save_classification_result(document_id: str, classification_result: str) -> bool:
    return _document_repository().save_classification_result(document_id, classification_result)


def update_document_info(document_id: str, updated_info: Dict) -> bool:
    return _document_repository().update(document_id, updated_info)


def save_document_to_chroma(
    filepath,
    document_id=None,
    use_refiner=True,
    save_chunk_info=True,
    full_content=None,
):
    return _vector_index_service().save_document_to_chroma(
        filepath,
        document_id=document_id,
        use_refiner=use_refiner,
        save_chunk_info=save_chunk_info,
        full_content=full_content,
        collection=get_chroma_collection(),
        update_document_info=update_document_info,
    )


def re_chunk_document(document_id: str, use_refiner: bool = True) -> bool:
    return _vector_index_service().re_chunk_document(
        document_id,
        use_refiner=use_refiner,
        get_document_info=get_document_info,
        get_chroma_collection=get_chroma_collection,
        save_document_to_chroma=save_document_to_chroma,
        update_document_info=update_document_info,
        fallback_roots=[BASE_DIR / "classified_docs", BASE_DIR / "doc"],
    )


def save_classification_table_record(table_payload: Dict, table_id: str | None = None):
    return _classification_table_repository().save(table_payload, table_id)


def get_classification_table_record(table_id: str):
    return _classification_table_repository().get(table_id)


def list_classification_table_records(limit: int = 50):
    return _classification_table_repository().list(limit)


def update_classification_tree_after_reclassify(document_id, old_classification, new_classification):
    return _bridge_reclassify(
        document_id,
        old_classification,
        new_classification,
        get_document_info=get_document_info,
    )


class ClassificationService:
    def __init__(self):
        self.topic_tree_service = TopicTreeService()

    def classify(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        classification_result = classify_document(doc_info)
        if not classification_result:
            raise AppServiceError(1005, "文档分类处理失败")

        result_data = classification_result.get("classification_result", {})
        categories = result_data.get("categories", [])
        actual_path = result_data.get("actual_path")
        if categories:
            save_classification_result(document_id, categories[0])
        if actual_path:
            update_document_info(document_id, {"filepath": actual_path})

        return {
            "document_id": document_id,
            "filename": doc_info.get("filename", ""),
            "categories": categories,
            "confidence": result_data.get("confidence", 0.0),
            "suggested_folders": result_data.get("suggested_folders", []),
        }

    def reclassify(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")

        old_classification = doc_info.get("classification_result")
        classification_result = classify_document(doc_info)
        if not classification_result:
            raise AppServiceError(1005, "文档分类处理失败")

        result_data = classification_result.get("classification_result", {})
        categories = result_data.get("categories", [])
        new_classification = categories[0] if categories else None
        actual_path = result_data.get("actual_path")

        if new_classification:
            save_classification_result(document_id, new_classification)
            if actual_path:
                update_document_info(document_id, {"filepath": actual_path})
            multi_level_info = get_multi_level_classifier().classify_document(get_document_info(document_id))
            update_classification_tree_after_reclassify(document_id, old_classification, multi_level_info)

        return {
            "document_id": document_id,
            "filename": doc_info.get("filename", ""),
            "old_classification": old_classification,
            "new_classification": new_classification,
            "categories": categories,
            "confidence": result_data.get("confidence", 0.0),
        }

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
                "classification_time": None,
            },
        )
        update_classification_tree_after_reclassify(document_id, old_classification, None)
        return {"document_id": document_id, "old_classification": old_classification}

    def get_categories(self) -> Dict:
        category_count: Dict[str, int] = {}
        for doc in get_all_documents():
            category = doc.get("classification_result", "未分类")
            category_count[category] = category_count.get(category, 0) + 1
        return {"categories": list(category_count.keys()), "document_count": category_count}

    def get_documents_by_category(self, category: str) -> Dict:
        docs = get_documents_by_classification(category)
        items = [
            {
                "id": doc.get("id"),
                "filename": doc.get("filename"),
                "file_type": doc.get("file_type"),
                "classification_result": doc.get("classification_result"),
            }
            for doc in docs
        ]
        return {"category": category, "total": len(items), "documents": items}

    def create_folder(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        if not doc_info.get("classification_result"):
            raise AppServiceError(1006, "文档尚未分类，请先执行分类")

        success, target_path = create_classification_directory(doc_info, [doc_info["classification_result"]])
        if not success:
            raise AppServiceError(1005, "分类目录创建失败")

        if target_path:
            update_document_info(document_id, {"filepath": target_path})
        return {"document_id": document_id, "target_path": target_path}

    def build_multi_level_tree(self, force_rebuild: bool) -> Dict:
        if force_rebuild:
            return build_and_save_classification_tree()
        return get_classification_tree() or build_and_save_classification_tree()

    def get_multi_level_tree(self) -> Dict:
        return get_classification_tree() or {"generated_at": "", "total_documents": 0, "tree": {}}

    def build_topic_tree(self, force_rebuild: bool = False) -> Dict:
        return self.topic_tree_service.build_topic_tree(force_rebuild=force_rebuild)

    def get_topic_tree(self) -> Dict:
        return self.topic_tree_service.get_topic_tree()

    def get_document_multi_level_info(self, document_id: str) -> Dict:
        doc_info = get_document_info(document_id)
        if not doc_info:
            raise AppServiceError(1001, f"文档ID: {document_id}")
        result = get_multi_level_classifier().classify_document(doc_info)
        if not result:
            raise AppServiceError(1005, "文档分类失败")
        return result

    def category_batch_rechunk(self, category: str, use_refiner: bool) -> Dict:
        docs = get_documents_by_classification(category)
        results = []
        for doc in docs:
            try:
                success = re_chunk_document(doc["id"], use_refiner=use_refiner)
                results.append({"document_id": doc["id"], "filename": doc.get("filename", ""), "success": success})
            except Exception as exc:
                results.append({"document_id": doc["id"], "filename": doc.get("filename", ""), "success": False, "error": str(exc)})

        success_count = sum(1 for item in results if item["success"])
        return {"category": category, "total": len(results), "success_count": success_count, "results": results}

    def category_batch_reclassify(self, category: str) -> Dict:
        docs = get_documents_by_classification(category)
        results = []
        for doc in docs:
            try:
                result = self.reclassify(doc["id"])
                results.append(
                    {
                        "document_id": doc["id"],
                        "filename": doc.get("filename", ""),
                        "success": True,
                        "old_classification": result.get("old_classification"),
                        "new_classification": result.get("new_classification"),
                    }
                )
            except Exception as exc:
                results.append({"document_id": doc["id"], "filename": doc.get("filename", ""), "success": False, "error": str(exc)})

        success_count = sum(1 for item in results if item["success"])
        return {"category": category, "total": len(results), "success_count": success_count, "results": results}

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
