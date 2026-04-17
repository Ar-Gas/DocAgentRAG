"""
动态语义主题树服务。

当前实现完全基于文档向量聚类 + LLM 命名，不再回退到关键词分组。
"""
import asyncio
import inspect
from datetime import datetime
from threading import Thread
from typing import Any, Dict, List

from app.infra.metadata_store import get_metadata_store
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.services.topic_clustering import TopicClustering
from app.services.document_label_resolver import resolve_document_label
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


def update_document_info(document_id: str, updated_info: Dict[str, Any]) -> bool:
    return _document_repository().update(document_id, updated_info)


class TopicTreeService:
    artifact_name = "topic_tree"
    schema_version = 3
    generation_method = "doc_embedding_cluster+fallback_label_contract"

    def __init__(self, max_topics: int = 10):
        self.max_topics = max_topics
        self.clustering = TopicClustering(max_topics=max_topics)
        self.labeler = TopicLabeler()

    def get_topic_tree(self) -> Dict[str, Any]:
        cached = self._load_valid_cached_artifact()
        if cached:
            self._sync_document_topic_assignments(cached)
            return cached
        return self.build_topic_tree(force_rebuild=True)

    def build_topic_tree(self, force_rebuild: bool = False) -> Dict[str, Any]:
        if not force_rebuild:
            cached = self._load_valid_cached_artifact()
            if cached:
                return cached

        raw_documents = [doc for doc in get_all_documents() if doc.get("id")]
        documents = [
            self._build_document_profile(doc)
            for doc in raw_documents
        ]
        documents = [doc for doc in documents if doc]

        if not documents:
            payload = self._build_payload([], total_documents=0, clustered_documents=0, excluded_documents=0)
            self._store().save_artifact(self.artifact_name, payload)
            return payload

        clusterable_documents, excluded_documents = self.clustering.build_document_vectors(documents)
        topics = self._build_topics(clusterable_documents) if clusterable_documents else []
        document_lookup = {doc["id"]: doc for doc in raw_documents if doc.get("id")}
        topics.extend(self._build_fallback_topics(excluded_documents, document_lookup))

        payload = self._build_payload(
            topics,
            total_documents=len(documents),
            clustered_documents=len(clusterable_documents),
            excluded_documents=len(excluded_documents),
        )
        self._store().save_artifact(self.artifact_name, payload)
        self._sync_document_topic_assignments(payload)
        return payload

    def classify_document(self, document_id: str, force_rebuild: bool = False) -> Dict[str, Any]:
        del force_rebuild
        tree = self.get_topic_tree()
        assignment = self._find_document_assignment(tree, document_id)
        if assignment:
            return assignment
        raise RuntimeError(f"document {document_id} is not assigned to any topic node")

    def get_category_overview(self) -> Dict[str, Any]:
        tree = self.get_topic_tree()
        categories: List[str] = []
        document_count: Dict[str, int] = {}

        for node, path in self._iter_leaf_topics(tree.get("topics") or []):
            label = node.get("label", "")
            if not label:
                continue
            categories.append(label)
            document_count[label] = int(node.get("document_count") or len(node.get("documents") or []))

        return {
            "categories": sorted(categories),
            "document_count": document_count,
        }

    def get_documents_by_topic(self, topic_key: str) -> Dict[str, Any]:
        normalized_key = (topic_key or "").strip()
        if not normalized_key:
            return {
                "category": "",
                "topic_id": None,
                "topic_path": [],
                "total": 0,
                "documents": [],
            }

        tree = self.get_topic_tree()
        for node, path in self._iter_topic_nodes(tree.get("topics") or []):
            if normalized_key not in {node.get("label"), node.get("topic_id")}:
                continue
            documents = [
                self._serialize_topic_document(doc, path)
                for doc in self._collect_documents(node)
            ]
            documents.sort(key=lambda item: (item.get("classification_result") or "", item.get("filename") or ""))
            return {
                "category": node.get("label", normalized_key),
                "topic_id": node.get("topic_id"),
                "topic_path": path,
                "total": len(documents),
                "documents": documents,
            }

        return {
            "category": normalized_key,
            "topic_id": None,
            "topic_path": [],
            "total": 0,
            "documents": [],
        }

    def get_legacy_tree_payload(self) -> Dict[str, Any]:
        tree = self.get_topic_tree()
        legacy_tree: Dict[str, Dict[str, List[str]]] = {}
        for topic in tree.get("topics") or []:
            parent_label = topic.get("label", "")
            children = topic.get("children") or []
            legacy_tree[parent_label] = {
                child.get("label", ""): [
                    item.get("document_id")
                    for item in child.get("documents") or []
                    if item.get("document_id")
                ]
                for child in children
                if child.get("label")
            }
            if not children and topic.get("documents"):
                legacy_tree[parent_label] = {
                    parent_label: [
                        item.get("document_id")
                        for item in topic.get("documents") or []
                        if item.get("document_id")
                    ]
                }
        return {
            "generated_at": tree.get("generated_at", ""),
            "total_documents": tree.get("total_documents", 0),
            "topic_count": tree.get("topic_count", 0),
            "tree": legacy_tree,
        }

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

    def _build_fallback_topics(
        self,
        excluded_documents: List[Dict[str, Any]],
        document_lookup: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not excluded_documents:
            return []

        resolved_documents = self._resolve_excluded_documents(excluded_documents, document_lookup)
        grouped_documents: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
            "兜底分类": {},
            "异常文档": {},
        }

        for document in resolved_documents:
            parent_label, child_label = self._route_excluded_document(document)
            grouped_documents[parent_label].setdefault(child_label, []).append(document)

        fallback_topics: List[Dict[str, Any]] = []
        parent_counter = 1
        for parent_label in ["兜底分类", "异常文档"]:
            children_map = grouped_documents[parent_label]
            if not children_map:
                continue

            children = []
            for child_counter, child_label in enumerate(sorted(children_map.keys()), start=1):
                docs = children_map[child_label]
                children.append(
                    {
                        "topic_id": f"topic-fallback-{parent_counter}-{child_counter}",
                        "label": child_label,
                        "keywords": [],
                        "document_count": len(docs),
                        "documents": [self._serialize_doc(item) for item in docs],
                        "children": [],
                    }
                )

            fallback_topics.append(
                {
                    "topic_id": f"topic-fallback-{parent_counter}",
                    "label": parent_label,
                    "keywords": [],
                    "document_count": sum(child["document_count"] for child in children),
                    "documents": [],
                    "children": children,
                }
            )
            parent_counter += 1

        return fallback_topics

    def _resolve_excluded_documents(
        self,
        excluded_documents: List[Dict[str, Any]],
        document_lookup: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return self._run_coroutine(
            self._resolve_excluded_documents_async(excluded_documents, document_lookup)
        )

    async def _resolve_excluded_documents_async(
        self,
        excluded_documents: List[Dict[str, Any]],
        document_lookup: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        resolved: List[Dict[str, Any]] = []
        for document in excluded_documents:
            document_id = document.get("document_id")
            if not document_id:
                continue

            raw_info = document_lookup.get(document_id) or {}
            doc_info = {
                **raw_info,
                **document,
                "id": raw_info.get("id") or document_id,
                "document_id": document_id,
            }
            label_result = resolve_document_label(document_id, doc_info)
            if inspect.isawaitable(label_result):
                label_result = await label_result
            label_result = label_result or {}
            resolved.append(
                {
                    **document,
                    "resolved_label": label_result.get("label"),
                    "resolved_is_error": bool(label_result.get("is_error")),
                }
            )
        return resolved

    @staticmethod
    def _route_excluded_document(document: Dict[str, Any]) -> tuple[str, str]:
        if document.get("exclude_reason") == "unusable_content":
            return "异常文档", "Error"

        label = str(document.get("resolved_label") or "").strip()
        if document.get("resolved_is_error") or label == "Error" or not label:
            return "异常文档", "Error"
        return "兜底分类", label

    @staticmethod
    def _run_coroutine(coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        output: Dict[str, Any] = {}
        error: Dict[str, Exception] = {}

        def runner() -> None:
            try:
                output["value"] = asyncio.run(coroutine)
            except Exception as exc:  # pragma: no cover
                error["value"] = exc

        worker = Thread(target=runner, daemon=True)
        worker.start()
        worker.join()

        if "value" in error:
            raise error["value"]
        return output.get("value", [])

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

    def _sync_document_topic_assignments(self, payload: Dict[str, Any]) -> None:
        documents = [
            doc
            for doc in get_all_documents()
            if doc.get("id")
        ]
        document_lookup = {
            doc.get("id"): doc
            for doc in documents
            if doc.get("id")
        }
        assignments = self._build_assignment_lookup(payload)

        generated_at = payload.get("generated_at")
        for document_id, doc_info in document_lookup.items():
            assignment = assignments.get(document_id)
            if assignment:
                topic_path = list(assignment.get("topic_path") or [])
                # classification_result is now owned by TaxonomyClassifier only
                update_payload = {
                    "topic_node_id": assignment.get("topic_id"),
                    "topic_label": assignment.get("topic_label"),
                    "topic_path": topic_path,
                    "topic_parent_label": topic_path[-2] if len(topic_path) > 1 else None,
                    "topic_tree_generated_at": generated_at,
                }
            else:
                update_payload = {
                    "topic_node_id": None,
                    "topic_label": None,
                    "topic_path": [],
                    "topic_parent_label": None,
                    "topic_tree_generated_at": generated_at,
                }

            if all(doc_info.get(key) == value for key, value in update_payload.items()):
                continue
            update_document_info(document_id, update_payload)

    def _build_assignment_lookup(self, payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        for node, path in self._iter_leaf_topics(payload.get("topics") or []):
            for doc in node.get("documents") or []:
                document_id = doc.get("document_id")
                if not document_id:
                    continue
                lookup[document_id] = {
                    "document_id": document_id,
                    "topic_id": node.get("topic_id"),
                    "topic_label": node.get("label", ""),
                    "topic_path": path,
                    "confidence": 1.0,
                }
        return lookup

    def _find_document_assignment(self, payload: Dict[str, Any], document_id: str) -> Dict[str, Any] | None:
        return self._build_assignment_lookup(payload).get(document_id)

    def _iter_topic_nodes(
        self,
        topics: List[Dict[str, Any]],
        parent_path: List[str] | None = None,
    ) -> List[tuple[Dict[str, Any], List[str]]]:
        parent_path = list(parent_path or [])
        rows: List[tuple[Dict[str, Any], List[str]]] = []
        for topic in topics:
            current_path = [*parent_path, topic.get("label", "")]
            rows.append((topic, current_path))
            rows.extend(self._iter_topic_nodes(topic.get("children") or [], current_path))
        return rows

    def _iter_leaf_topics(
        self,
        topics: List[Dict[str, Any]],
        parent_path: List[str] | None = None,
    ) -> List[tuple[Dict[str, Any], List[str]]]:
        leaves: List[tuple[Dict[str, Any], List[str]]] = []
        for topic, path in self._iter_topic_nodes(topics, parent_path):
            if not topic.get("children"):
                leaves.append((topic, path))
        return leaves

    def _collect_documents(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        documents = list(node.get("documents") or [])
        for child in node.get("children") or []:
            documents.extend(self._collect_documents(child))
        return documents

    @staticmethod
    def _serialize_topic_document(doc: Dict[str, Any], topic_path: List[str]) -> Dict[str, Any]:
        label = topic_path[-1] if topic_path else None
        return {
            "id": doc.get("document_id"),
            "document_id": doc.get("document_id"),
            "filename": doc.get("filename", ""),
            "file_type": doc.get("file_type", ""),
            "classification_result": label,
            "topic_path": topic_path,
            "created_at_iso": doc.get("created_at_iso"),
            "excerpt": doc.get("excerpt", ""),
            "keywords": doc.get("keywords", []),
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
