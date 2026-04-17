from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from app.infra.embedding_provider import embed_text
from app.infra.repositories.document_artifact_repository import DocumentArtifactRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.infra.vector_store import get_block_collection
from app.services.document_label_resolver import is_error_document
from config import DATA_DIR


def _artifact_repository() -> DocumentArtifactRepository:
    return DocumentArtifactRepository(data_dir=DATA_DIR)


def _segment_repository() -> DocumentSegmentRepository:
    return DocumentSegmentRepository(data_dir=DATA_DIR)


def get_document_artifact(document_id: str, artifact_type: str = "reader_blocks") -> Dict[str, Any] | None:
    return _artifact_repository().get(document_id, artifact_type)


def list_document_segments(document_id: str) -> List[Dict[str, Any]]:
    return _segment_repository().list(document_id)


def list_document_block_embeddings(document_id: str) -> List[Dict[str, Any]]:
    collection = get_block_collection()
    if not document_id or collection is None:
        return []

    try:
        payload = collection.get(
            where={"document_id": document_id},
            include=["embeddings", "metadatas", "documents"],
        )
    except Exception:
        return []

    embeddings = payload.get("embeddings") or []
    metadatas = payload.get("metadatas") or []
    documents = payload.get("documents") or []
    row_count = max(len(embeddings), len(metadatas), len(documents))

    results: List[Dict[str, Any]] = []
    for index in range(row_count):
        embedding = embeddings[index] if index < len(embeddings) else None
        if embedding is None:
            continue
        results.append(
            {
                "embedding": list(embedding),
                "metadata": metadatas[index] if index < len(metadatas) else {},
                "content": documents[index] if index < len(documents) else "",
            }
        )
    return results


class TopicClustering:
    def __init__(self, max_topics: int = 10, representative_limit: int = 5):
        self.max_topics = max_topics
        self.representative_limit = representative_limit

    def build_document_vectors(
        self, documents: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        prepared: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []

        for document in documents:
            document_id = document.get("document_id", "")
            if is_error_document(document_id, document):
                excluded.append({**document, "exclude_reason": "unusable_content"})
                continue

            vector = self._derive_document_vector(document)
            if vector is None:
                excluded.append({**document, "exclude_reason": "missing_vector"})
                continue
            prepared.append({**document, "vector": vector})

        if not prepared:
            return [], excluded

        # Keep only the dominant vector dimension so clustering remains coherent.
        dimension_counts = Counter(len(item["vector"]) for item in prepared)
        dominant_dimension = dimension_counts.most_common(1)[0][0]

        filtered = []
        for item in prepared:
            if len(item["vector"]) == dominant_dimension:
                filtered.append(item)
            else:
                excluded.append({**item, "exclude_reason": "dimension_mismatch"})
        return filtered, excluded

    def cluster_documents(self, documents: List[Dict[str, Any]], level: int) -> List[Dict[str, Any]]:
        if not documents:
            return []
        if len(documents) == 1:
            only = documents[0]
            return [
                {
                    "documents": [only],
                    "representatives": [only],
                    "center": list(only["vector"]),
                }
            ]

        vectors = np.asarray([item["vector"] for item in documents], dtype=float)
        labels, centers = self._run_kmeans(vectors, level)

        grouped_indices: Dict[int, List[int]] = defaultdict(list)
        for index, label in enumerate(labels):
            grouped_indices[int(label)].append(index)

        clusters: List[Dict[str, Any]] = []
        for label, indices in grouped_indices.items():
            cluster_documents = [documents[index] for index in indices]
            center = np.asarray(centers[label], dtype=float)
            clusters.append(
                {
                    "documents": cluster_documents,
                    "representatives": self.pick_representatives(cluster_documents, center),
                    "center": center.tolist(),
                }
            )

        sorted_clusters = sorted(
            clusters,
            key=lambda item: (
                -len(item["documents"]),
                item["documents"][0].get("filename", ""),
            ),
        )
        return sorted_clusters

    def pick_representatives(
        self, documents: List[Dict[str, Any]], center: np.ndarray, limit: int | None = None
    ) -> List[Dict[str, Any]]:
        actual_limit = limit or self.representative_limit
        ranked = sorted(
            documents,
            key=lambda item: (
                float(np.linalg.norm(np.asarray(item["vector"], dtype=float) - center)),
                item.get("filename", ""),
            ),
        )
        return ranked[:actual_limit]

    def _derive_document_vector(self, document: Dict[str, Any]) -> List[float] | None:
        block_vectors = []
        for item in list_document_block_embeddings(document.get("document_id", "")):
            embedding = item.get("embedding")
            normalized = self._normalize_vector(embedding)
            if normalized is not None:
                block_vectors.append(normalized)

        if block_vectors:
            averaged = np.mean(np.asarray(block_vectors, dtype=float), axis=0)
            normalized_average = self._normalize_vector(averaged.tolist())
            if normalized_average is not None:
                return normalized_average

        block_text_source = self._build_block_text_source(document.get("document_id", ""))
        if block_text_source:
            embedded_block_text = embed_text(block_text_source)
            normalized_block_text = self._normalize_vector(embedded_block_text)
            if normalized_block_text is not None:
                return normalized_block_text

        summary_source = (
            document.get("summary_source")
            or document.get("excerpt")
            or document.get("filename")
            or ""
        ).strip()
        if not summary_source:
            return None

        embedded = embed_text(summary_source)
        return self._normalize_vector(embedded)

    def _build_block_text_source(self, document_id: str) -> str:
        if not document_id:
            return ""

        artifact = get_document_artifact(document_id, "reader_blocks") or {}
        blocks = (artifact.get("payload") or {}).get("blocks") or []
        artifact_text = "\n".join(
            block.get("text", "").strip()
            for block in sorted(blocks, key=lambda item: item.get("block_index", 0))
            if block.get("text")
        )
        if artifact_text.strip():
            return artifact_text[:2500]

        segment_text = "\n".join(
            segment.get("content", "").strip()
            for segment in sorted(list_document_segments(document_id), key=lambda item: item.get("segment_index", 0))
            if segment.get("content")
        )
        return segment_text[:2500]

    def _run_kmeans(self, vectors: np.ndarray, level: int) -> Tuple[np.ndarray, np.ndarray]:
        sample_count = len(vectors)
        if sample_count <= 2:
            labels = np.zeros(sample_count, dtype=int)
            centers = np.asarray([vectors.mean(axis=0)], dtype=float)
            return labels, centers

        best_labels = np.zeros(sample_count, dtype=int)
        best_centers = np.asarray([vectors.mean(axis=0)], dtype=float)
        best_score = None

        upper_bound = min(self.max_topics, sample_count - 1)
        if level == 2:
            upper_bound = min(upper_bound, max(2, sample_count // 2))

        for cluster_count in range(2, upper_bound + 1):
            model = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
            labels = model.fit_predict(vectors)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(vectors, labels)
            if best_score is None or score > best_score:
                best_score = score
                best_labels = labels
                best_centers = model.cluster_centers_

        return best_labels, best_centers

    @staticmethod
    def _normalize_vector(vector: List[float] | np.ndarray | None) -> List[float] | None:
        if vector is None:
            return None
        array = np.asarray(vector, dtype=float)
        if array.size == 0:
            return None
        norm = float(np.linalg.norm(array))
        if norm == 0.0:
            return None
        normalized = array / norm
        return normalized.tolist()
