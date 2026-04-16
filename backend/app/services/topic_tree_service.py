"""
动态语义主题树服务。

当前实现完全基于文档向量聚类 + LLM 命名，不再回退到关键词分组。
"""
from datetime import datetime
from typing import Any, Dict, List

from app.infra.metadata_store import get_metadata_store
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.services.topic_clustering import TopicClustering
from app.services.topic_labeler import TopicLabeler
from config import DATA_DIR


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def _content_repository() -> DocumentContentRepository:
    return DocumentContentRepository(data_dir=DATA_DIR)


def _segment_repository() -> DocumentSegmentRepository:
    return DocumentSegmentRepository(data_dir=DATA_DIR)


def get_all_documents():
    return _document_repository().list_all()


def get_document_content_record(document_id: str):
    return _content_repository().get(document_id)


def list_document_segments(document_id: str):
    return _segment_repository().list(document_id)


class TopicTreeService:
    artifact_name = "topic_tree"
    schema_version = 2
    generation_method = "doc_embedding_cluster+llm_label"

    def __init__(self, max_topics: int = 10):
        self.max_topics = max_topics
        self.clustering = TopicClustering(max_topics=max_topics)
        self.labeler = TopicLabeler()

    def get_topic_tree(self) -> Dict[str, Any]:
        cached = self._load_valid_cached_artifact()
        if cached:
            return cached
        return self.build_topic_tree(force_rebuild=True)

    def build_topic_tree(self, force_rebuild: bool = False) -> Dict[str, Any]:
        if not force_rebuild:
            cached = self._load_valid_cached_artifact()
            if cached:
                return cached

        documents = [
            self._build_document_profile(doc)
            for doc in get_all_documents()
            if doc.get("id")
        ]
        documents = [doc for doc in documents if doc]

        if not documents:
            payload = self._build_payload([], total_documents=0, clustered_documents=0, excluded_documents=0)
            self._store().save_artifact(self.artifact_name, payload)
            return payload

        clusterable_documents, excluded_documents = self.clustering.build_document_vectors(documents)
        if not clusterable_documents:
            raise RuntimeError("无法为任何文档生成主题聚类向量")

        topics = self._build_topics(clusterable_documents)
        payload = self._build_payload(
            topics,
            total_documents=len(documents),
            clustered_documents=len(clusterable_documents),
            excluded_documents=len(excluded_documents),
        )
        self._store().save_artifact(self.artifact_name, payload)
        return payload

    def _store(self):
        return get_metadata_store(data_dir=DATA_DIR)

    def _load_valid_cached_artifact(self) -> Dict[str, Any] | None:
        cached = self._store().load_artifact(self.artifact_name)
        if self._is_valid_topic_tree_artifact(cached):
            return cached
        return None

    def _is_valid_topic_tree_artifact(self, payload: Dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        if int(payload.get("schema_version") or 0) < self.schema_version:
            return False
        if payload.get("generation_method") != self.generation_method:
            return False

        topics = payload.get("topics")
        if not isinstance(topics, list):
            return False

        for topic in topics:
            if not isinstance(topic, dict):
                return False
            children = topic.get("children")
            if children is None:
                return False
            if topic.get("documents"):
                return False
            if not isinstance(children, list):
                return False
        return True

    def _build_document_profile(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        document_id = doc.get("id")
        if not document_id:
            return {}

        content_record = get_document_content_record(document_id) or {}
        segments = list_document_segments(document_id)
        preview = (
            content_record.get("preview_content")
            or doc.get("preview_content")
            or (segments[0].get("content") if segments else "")
            or ""
        )
        segment_text = "\n".join(
            seg.get("content", "").strip()
            for seg in segments[:3]
            if seg.get("content")
        )
        full_content = (content_record.get("full_content") or "")[:1500]
        summary_source = "\n".join(
            item.strip()
            for item in [
                doc.get("filename", ""),
                preview,
                segment_text,
                full_content,
            ]
            if item and str(item).strip()
        )

        return {
            "document_id": document_id,
            "filename": doc.get("filename", ""),
            "file_type": doc.get("file_type", ""),
            "classification_result": doc.get("classification_result") or "",
            "created_at_iso": doc.get("created_at_iso"),
            "excerpt": preview[:200],
            "summary_source": summary_source[:2500],
            "keywords": [],
        }

    def _build_topics(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        parent_clusters = self.clustering.cluster_documents(documents, level=1)
        seen_ids = set()
        topics = []

        for parent_index, parent_cluster in enumerate(parent_clusters[: self.max_topics], start=1):
            children = []
            parent_label = self.labeler.label_parent_topic(parent_cluster["representatives"])

            child_clusters = self.clustering.cluster_documents(parent_cluster["documents"], level=2)
            for child_index, child_cluster in enumerate(child_clusters, start=1):
                leaf_documents = []
                for document in child_cluster["documents"]:
                    document_id = document.get("document_id")
                    if document_id and document_id not in seen_ids:
                        seen_ids.add(document_id)
                        leaf_documents.append(document)

                if not leaf_documents:
                    continue

                child_label = self.labeler.label_child_topic(
                    parent_label["label"],
                    child_cluster["representatives"],
                )
                children.append(
                    {
                        "topic_id": f"topic-{parent_index}-{child_index}",
                        "label": child_label["label"],
                        "keywords": [],
                        "document_count": len(leaf_documents),
                        "documents": [self._serialize_doc(item) for item in leaf_documents],
                        "children": [],
                    }
                )

            if not children:
                continue

            topics.append(
                {
                    "topic_id": f"topic-{parent_index}",
                    "label": parent_label["label"],
                    "keywords": [],
                    "document_count": sum(child["document_count"] for child in children),
                    "documents": [],
                    "children": children,
                }
            )

        return topics

    def _build_payload(
        self,
        topics: List[Dict[str, Any]],
        *,
        total_documents: int,
        clustered_documents: int,
        excluded_documents: int,
    ) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": datetime.now().isoformat(),
            "total_documents": total_documents,
            "clustered_documents": clustered_documents,
            "excluded_documents": excluded_documents,
            "topic_count": len(topics),
            "generation_method": self.generation_method,
            "topics": topics,
        }

    @staticmethod
    def _serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "document_id": doc.get("document_id"),
            "filename": doc.get("filename", ""),
            "file_type": doc.get("file_type", ""),
            "classification_result": doc.get("classification_result"),
            "created_at_iso": doc.get("created_at_iso"),
            "excerpt": doc.get("excerpt", ""),
            "keywords": doc.get("keywords", []),
        }
