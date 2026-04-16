import asyncio
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.classification as classification_api  # noqa: E402
import app.services.topic_tree_service as topic_tree_service_module  # noqa: E402
from app.services.topic_tree_service import TopicTreeService  # noqa: E402


def _sample_documents():
    return [
        {
            "id": "doc-1",
            "filename": "audit-plan.pdf",
            "file_type": ".pdf",
            "classification_result": "财务",
            "created_at_iso": "2026-03-20T10:00:00",
        },
        {
            "id": "doc-2",
            "filename": "audit-report.pdf",
            "file_type": ".pdf",
            "classification_result": "采购",
            "created_at_iso": "2026-03-21T10:00:00",
        },
        {
            "id": "doc-3",
            "filename": "supplier-comparison.xlsx",
            "file_type": ".xlsx",
            "classification_result": "人事",
            "created_at_iso": "2026-03-22T10:00:00",
        },
    ]


def _content_record(document_id):
    records = {
        "doc-1": {
            "preview_content": "年度审计计划、审计范围、执行安排",
            "full_content": "围绕年度审计计划与财务核查展开。",
        },
        "doc-2": {
            "preview_content": "年度审计报告、问题闭环、整改跟踪",
            "full_content": "围绕年度审计结论与整改事项展开。",
        },
        "doc-3": {
            "preview_content": "供应商比价、采购方案、合同条款",
            "full_content": "围绕供应商比价与采购执行方案展开。",
        },
    }
    return records[document_id]


def _segments(document_id):
    payload = {
        "doc-1": [{"content": "审计范围覆盖收入、成本与报销。"}],
        "doc-2": [{"content": "审计发现与整改计划同步推进。"}],
        "doc-3": [{"content": "供应商报价对比与合同条件评估。"}],
    }
    return payload[document_id]


class FakeStore:
    def __init__(self, cached=None):
        self.cached = cached
        self.saved = {}

    def save_artifact(self, name, payload):
        self.saved[name] = payload
        return True

    def load_artifact(self, name):
        return self.cached


class FakeTopicClustering:
    def __init__(self, *args, **kwargs):
        pass

    def build_document_vectors(self, documents):
        prepared = []
        for index, document in enumerate(documents, start=1):
            prepared.append({**document, "vector": [float(index), 0.0]})
        return prepared, []

    def cluster_documents(self, documents, level):
        if level == 1:
            return [
                {
                    "documents": documents,
                    "representatives": documents[:2],
                    "center": [1.0, 0.0],
                }
            ]
        return [
            {
                "documents": documents[:2],
                "representatives": documents[:2],
                "center": [1.0, 0.0],
            },
            {
                "documents": documents[2:],
                "representatives": documents[2:],
                "center": [3.0, 0.0],
            },
        ]


class FakeTopicLabeler:
    def label_parent_topic(self, representatives):
        filenames = [item["filename"] for item in representatives]
        assert "audit-plan.pdf" in filenames
        return {"label": "财务治理", "summary": "围绕审计与整改治理"}

    def label_child_topic(self, parent_label, representatives):
        assert parent_label == "财务治理"
        filenames = [item["filename"] for item in representatives]
        if "supplier-comparison.xlsx" in filenames:
            return {"label": "供应商比价", "summary": "围绕供应商报价比选"}
        return {"label": "年度审计", "summary": "围绕年度审计计划与报告"}


def _patch_common_dependencies(monkeypatch, cached=None):
    store = FakeStore(cached=cached)
    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", _sample_documents)
    monkeypatch.setattr(topic_tree_service_module, "get_document_content_record", _content_record)
    monkeypatch.setattr(topic_tree_service_module, "list_document_segments", _segments)
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: True)
    monkeypatch.setattr(topic_tree_service_module, "get_metadata_store", lambda data_dir=None: store)
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClustering, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "TopicLabeler", FakeTopicLabeler, raising=False)
    return store


def test_build_topic_tree_uses_cluster_and_llm_labels_not_classification_results(monkeypatch):
    store = _patch_common_dependencies(monkeypatch)

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    assert tree["schema_version"] == 2
    assert tree["generation_method"] == "doc_embedding_cluster+llm_label"
    assert tree["total_documents"] == 3
    assert tree["clustered_documents"] == 3
    assert tree["excluded_documents"] == 0
    assert [topic["label"] for topic in tree["topics"]] == ["财务治理"]
    assert [child["label"] for child in tree["topics"][0]["children"]] == ["年度审计", "供应商比价"]
    assert store.saved["topic_tree"]["schema_version"] == 2


def test_build_topic_tree_places_each_document_in_exactly_one_leaf(monkeypatch):
    _patch_common_dependencies(monkeypatch)

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    leaf_ids = [
        document["document_id"]
        for topic in tree["topics"]
        for child in topic["children"]
        for document in child["documents"]
    ]
    assert sorted(leaf_ids) == ["doc-1", "doc-2", "doc-3"]
    assert len(leaf_ids) == len(set(leaf_ids))


def test_get_topic_tree_ignores_legacy_cached_payload_and_rebuilds(monkeypatch):
    legacy_cache = {
        "generated_at": "2026-03-24T10:00:00",
        "generation_method": "classification_result+corpus_keywords",
        "topics": [{"topic_id": "topic-1", "label": "财务", "documents": []}],
    }
    _patch_common_dependencies(monkeypatch, cached=legacy_cache)

    tree = TopicTreeService().get_topic_tree()

    assert tree["schema_version"] == 2
    assert tree["generation_method"] == "doc_embedding_cluster+llm_label"
    assert tree["topics"][0]["label"] == "财务治理"


def test_build_document_vectors_use_block_payload_before_summary_fallback(monkeypatch):
    from app.services.topic_clustering import TopicClustering
    import app.services.topic_clustering as topic_clustering_module

    monkeypatch.setattr(
        topic_clustering_module,
        "list_document_chunk_embeddings",
        lambda document_id: (_ for _ in ()).throw(AssertionError("legacy chunk embeddings should not be used")),
        raising=False,
    )
    monkeypatch.setattr(
        topic_clustering_module,
        "get_document_artifact",
        lambda document_id, artifact_type="reader_blocks": (
            {
                "payload": {
                    "blocks": [
                        {
                            "block_id": "doc-1:block-v1:0",
                            "block_index": 0,
                            "text": "年度审计计划与范围",
                        }
                    ]
                }
            }
            if document_id == "doc-1" and artifact_type == "reader_blocks"
            else None
        ),
        raising=False,
    )
    monkeypatch.setattr(
        topic_clustering_module,
        "list_document_segments",
        lambda document_id: [],
        raising=False,
    )
    monkeypatch.setattr(
        topic_clustering_module,
        "embed_text",
        lambda text: [3.0, 0.0] if "年度审计" in text else ([0.0, 2.0] if "供应商比价" in text else None),
    )

    clustering = TopicClustering()
    prepared, excluded = clustering.build_document_vectors(
        [
            {
                "document_id": "doc-1",
                "filename": "audit-plan.pdf",
                "summary_source": "年度审计计划",
                "excerpt": "年度审计计划",
            },
            {
                "document_id": "doc-2",
                "filename": "supplier-comparison.xlsx",
                "summary_source": "供应商比价与采购方案",
                "excerpt": "供应商比价与采购方案",
            },
        ]
    )

    assert sorted(item["document_id"] for item in prepared) == ["doc-1", "doc-2"]
    assert excluded == []
    vectors = {item["document_id"]: item["vector"] for item in prepared}
    assert vectors["doc-1"] == [1.0, 0.0]
    assert vectors["doc-2"] == [0.0, 1.0]


def test_topic_tree_api_returns_service_payload(monkeypatch):
    mock_get_topic_tree = Mock(
        return_value={
            "generated_at": "2026-03-24T10:00:00",
            "schema_version": 2,
            "total_documents": 2,
            "clustered_documents": 2,
            "excluded_documents": 0,
            "topics": [{"topic_id": "topic-1", "label": "财务治理", "children": []}],
        }
    )
    monkeypatch.setattr(classification_api.classification_service, "get_topic_tree", mock_get_topic_tree)

    body = asyncio.run(classification_api.get_topic_tree())

    assert body["code"] == 200
    assert body["data"]["schema_version"] == 2
    assert body["data"]["total_documents"] == 2
    mock_get_topic_tree.assert_called_once()
