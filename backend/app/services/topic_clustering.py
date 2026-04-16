from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from app.infra.embedding_provider import embed_text
from app.infra.vector_store import get_chroma_collection
from app.services.document_vector_index_service import DocumentVectorIndexService


def _vector_index_service() -> DocumentVectorIndexService:
    return DocumentVectorIndexService()


def list_document_chunk_embeddings(document_id: str) -> List[Dict[str, Any]]:
    return _vector_index_service().list_document_chunk_embeddings(
        document_id,
        collection=get_chroma_collection(),
    )


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
            vector = self._derive_document_vector(document)
            if vector is None:
                excluded.append(document)
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
                excluded.append(item)
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

        return sorted(
            clusters,
            key=lambda item: (
                -len(item["documents"]),
                item["documents"][0].get("filename", ""),
            ),
        )

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
        chunk_vectors = []
        for item in list_document_chunk_embeddings(document.get("document_id", "")):
            embedding = item.get("embedding")
            normalized = self._normalize_vector(embedding)
            if normalized is not None:
                chunk_vectors.append(normalized)

        if chunk_vectors:
            averaged = np.mean(np.asarray(chunk_vectors, dtype=float), axis=0)
            normalized_average = self._normalize_vector(averaged.tolist())
            if normalized_average is not None:
                return normalized_average

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
