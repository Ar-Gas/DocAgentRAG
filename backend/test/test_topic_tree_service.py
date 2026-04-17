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

    assert tree["schema_version"] == 3
    assert tree["generation_method"] == "doc_embedding_cluster+fallback_label_contract"
    assert tree["total_documents"] == 3
    assert tree["clustered_documents"] == 3
    assert tree["excluded_documents"] == 0
    assert [topic["label"] for topic in tree["topics"]] == ["财务治理"]
    assert [child["label"] for child in tree["topics"][0]["children"]] == ["年度审计", "供应商比价"]
    assert store.saved["topic_tree"]["schema_version"] == 3


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

    assert tree["schema_version"] == 3
    assert tree["generation_method"] == "doc_embedding_cluster+fallback_label_contract"
    assert tree["topics"][0]["label"] == "财务治理"


def test_classify_document_force_rebuild_flag_does_not_rebuild_tree(monkeypatch):
    service = TopicTreeService()
    tree = {
        "topics": [
            {
                "topic_id": "topic-1",
                "label": "财务治理",
                "children": [
                    {
                        "topic_id": "topic-1-1",
                        "label": "年度审计",
                        "documents": [{"document_id": "doc-1"}],
                        "children": [],
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(service, "get_topic_tree", lambda: tree)
    monkeypatch.setattr(
        service,
        "build_topic_tree",
        lambda force_rebuild=False: (_ for _ in ()).throw(
            AssertionError("classify_document should not force rebuild the topic tree")
        ),
    )

    assignment = service.classify_document("doc-1", force_rebuild=True)

    assert assignment["topic_id"] == "topic-1-1"
    assert assignment["topic_label"] == "年度审计"
    assert assignment["topic_path"] == ["财务治理", "年度审计"]


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


def test_build_document_vectors_marks_unusable_content_as_excluded(monkeypatch):
    from app.services.topic_clustering import TopicClustering
    import app.services.topic_clustering as topic_clustering_module

    monkeypatch.setattr(
        topic_clustering_module,
        "list_document_block_embeddings",
        lambda document_id: [],
        raising=False,
    )
    monkeypatch.setattr(
        topic_clustering_module,
        "get_document_artifact",
        lambda document_id, artifact_type="reader_blocks": None,
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
        lambda text: [3.0, 0.0] if "年度审计" in text else [0.0, 3.0],
        raising=False,
    )
    monkeypatch.setattr(
        topic_clustering_module,
        "is_error_document",
        lambda document_id, doc_info: document_id == "doc-2",
        raising=False,
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
                "filename": "broken.docx",
                "summary_source": "Word处理失败: Package not found at '/tmp/broken.docx'",
                "excerpt": "Word处理失败: Package not found at '/tmp/broken.docx'",
            },
        ]
    )

    assert [item["document_id"] for item in prepared] == ["doc-1"]
    assert len(excluded) == 1
    assert excluded[0]["document_id"] == "doc-2"
    assert excluded[0]["exclude_reason"] == "unusable_content"


def test_build_topic_tree_adds_fallback_topics_for_excluded_documents(monkeypatch):
    updates = []
    store = FakeStore()

    def documents():
        return [
            {"id": "doc-1", "filename": "audit-plan.pdf", "file_type": ".pdf", "classification_result": "年度审计", "created_at_iso": "2026-04-01T10:00:00"},
            {"id": "doc-2", "filename": "labor-contract.docx", "file_type": ".docx", "classification_result": None, "created_at_iso": "2026-04-02T10:00:00"},
            {"id": "doc-3", "filename": "broken.docx", "file_type": ".docx", "classification_result": None, "created_at_iso": "2026-04-03T10:00:00"},
        ]

    class FakeTopicClusteringWithExcluded:
        def __init__(self, *args, **kwargs):
            pass

        def build_document_vectors(self, docs):
            return (
                [{**docs[0], "vector": [1.0, 0.0]}],
                [
                    {**docs[1], "exclude_reason": "missing_vector"},
                    {**docs[2], "exclude_reason": "unusable_content"},
                ],
            )

        def cluster_documents(self, docs, level):
            return [{"documents": docs, "representatives": docs[:1], "center": [1.0, 0.0]}]

    class FakeTopicLabelerWithExcluded:
        def label_parent_topic(self, representatives):
            return {"label": "财务治理", "summary": "围绕审计与整改治理"}

        def label_child_topic(self, parent_label, representatives):
            return {"label": "年度审计", "summary": "围绕年度审计计划与报告"}

    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", documents)
    monkeypatch.setattr(topic_tree_service_module, "get_document_content_record", lambda document_id: {
        "doc-1": {"preview_content": "年度审计计划与整改安排"},
        "doc-2": {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
        "doc-3": {"preview_content": "Word处理失败: Package not found at '/tmp/broken.docx'"},
    }[document_id])
    monkeypatch.setattr(topic_tree_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "TopicLabeler", FakeTopicLabelerWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: updates.append((document_id, updated_info)) or True)
    monkeypatch.setattr(topic_tree_service_module, "get_metadata_store", lambda data_dir=None: store)
    def resolve_document_label(document_id, doc_info):
        return {
            "doc-2": {
                "label": "劳动合同",
                "source_text": (doc_info or {}).get("preview_content", ""),
                "is_error": False,
                "source": "test_stub",
            },
            "doc-3": {
                "label": "Error",
                "source_text": (doc_info or {}).get("preview_content", ""),
                "is_error": True,
                "source": "test_stub",
            },
        }.get(
            document_id,
            {
                "label": None,
                "source_text": (doc_info or {}).get("preview_content", ""),
                "is_error": False,
                "source": "test_stub",
            },
        )

    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", resolve_document_label, raising=False)

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    fallback_parent = next(topic for topic in tree["topics"] if topic["label"] == "兜底分类")
    error_parent = next(topic for topic in tree["topics"] if topic["label"] == "异常文档")

    assert [child["label"] for child in fallback_parent["children"]] == ["劳动合同"]
    assert [child["label"] for child in error_parent["children"]] == ["Error"]
    assert fallback_parent["children"][0]["documents"][0]["document_id"] == "doc-2"
    assert error_parent["children"][0]["documents"][0]["document_id"] == "doc-3"
    assert any(
        document_id == "doc-2"
        and payload["topic_label"] == "劳动合同"
        and payload["topic_path"] == ["兜底分类", "劳动合同"]
        and "classification_result" not in payload
        for document_id, payload in updates
    )
    assert any(
        document_id == "doc-3"
        and payload["topic_label"] == "Error"
        and payload["topic_path"] == ["异常文档", "Error"]
        and "classification_result" not in payload
        for document_id, payload in updates
    )
    assert "topic_tree" in store.saved


def test_build_topic_tree_profile_text_routes_excluded_document_to_fallback_topic(monkeypatch):
    updates = []
    resolved_inputs = {}
    store = FakeStore()

    def documents():
        return [
            {
                "id": "doc-1",
                "filename": "audit-plan.pdf",
                "file_type": ".pdf",
                "classification_result": "年度审计",
                "created_at_iso": "2026-04-01T10:00:00",
                "preview_content": "年度审计计划与整改安排",
            },
            {
                "id": "doc-2",
                "filename": "labor-contract.docx",
                "file_type": ".docx",
                "classification_result": None,
                "created_at_iso": "2026-04-02T10:00:00",
                "preview_content": "",
                "full_content": "",
            },
        ]

    class FakeTopicClusteringWithExcluded:
        def __init__(self, *args, **kwargs):
            pass

        def build_document_vectors(self, docs):
            return (
                [{**docs[0], "vector": [1.0, 0.0]}],
                [{**docs[1], "exclude_reason": "missing_vector"}],
            )

        def cluster_documents(self, docs, level):
            return [{"documents": docs, "representatives": docs[:1], "center": [1.0, 0.0]}]

    class FakeTopicLabelerWithExcluded:
        def label_parent_topic(self, representatives):
            return {"label": "财务治理", "summary": "围绕审计与整改治理"}

        def label_child_topic(self, parent_label, representatives):
            return {"label": "年度审计", "summary": "围绕年度审计计划与报告"}

    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", documents)
    monkeypatch.setattr(
        topic_tree_service_module,
        "get_document_content_record",
        lambda document_id: {"doc-1": {"preview_content": "年度审计计划与整改安排"}, "doc-2": {}}[document_id],
    )
    monkeypatch.setattr(
        topic_tree_service_module,
        "list_document_segments",
        lambda document_id: (
            [{"content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"}]
            if document_id == "doc-2"
            else []
        ),
    )
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "TopicLabeler", FakeTopicLabelerWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: updates.append((document_id, updated_info)) or True)
    monkeypatch.setattr(topic_tree_service_module, "get_metadata_store", lambda data_dir=None: store)

    def resolve_document_label(document_id, doc_info):
        resolved_inputs[document_id] = dict(doc_info or {})
        profile_text = f"{(doc_info or {}).get('excerpt', '')}\n{(doc_info or {}).get('summary_source', '')}"
        if document_id == "doc-2" and "劳动合同" in profile_text:
            return {
                "label": "劳动合同",
                "source_text": profile_text,
                "is_error": False,
                "source": "test_profile_text",
            }
        return {
            "label": "Error",
            "source_text": profile_text,
            "is_error": True,
            "source": "test_profile_text",
        }

    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", resolve_document_label, raising=False)

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    fallback_parent = next(topic for topic in tree["topics"] if topic["label"] == "兜底分类")
    assert [child["label"] for child in fallback_parent["children"]] == ["劳动合同"]
    assert fallback_parent["children"][0]["documents"][0]["document_id"] == "doc-2"
    assert "劳动合同" in resolved_inputs["doc-2"].get("excerpt", "")
    assert "劳动合同" in resolved_inputs["doc-2"].get("summary_source", "")
    assert any(
        document_id == "doc-2"
        and payload["topic_label"] == "劳动合同"
        and payload["topic_path"] == ["兜底分类", "劳动合同"]
        and "classification_result" not in payload
        for document_id, payload in updates
    )
    assert "topic_tree" in store.saved


def test_build_topic_tree_resolves_excluded_documents_with_async_resolver_inside_active_loop(monkeypatch):
    updates = []
    store = FakeStore()

    def documents():
        return [
            {"id": "doc-1", "filename": "audit-plan.pdf", "file_type": ".pdf", "classification_result": "年度审计", "created_at_iso": "2026-04-01T10:00:00"},
            {"id": "doc-2", "filename": "labor-contract.docx", "file_type": ".docx", "classification_result": None, "created_at_iso": "2026-04-02T10:00:00"},
        ]

    class FakeTopicClusteringWithExcluded:
        def __init__(self, *args, **kwargs):
            pass

        def build_document_vectors(self, docs):
            return (
                [{**docs[0], "vector": [1.0, 0.0]}],
                [{**docs[1], "exclude_reason": "missing_vector"}],
            )

        def cluster_documents(self, docs, level):
            return [{"documents": docs, "representatives": docs[:1], "center": [1.0, 0.0]}]

    class FakeTopicLabelerWithExcluded:
        def label_parent_topic(self, representatives):
            return {"label": "财务治理", "summary": "围绕审计与整改治理"}

        def label_child_topic(self, parent_label, representatives):
            return {"label": "年度审计", "summary": "围绕年度审计计划与报告"}

    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", documents)
    monkeypatch.setattr(
        topic_tree_service_module,
        "get_document_content_record",
        lambda document_id: {
            "doc-1": {"preview_content": "年度审计计划与整改安排"},
            "doc-2": {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
        }[document_id],
    )
    monkeypatch.setattr(topic_tree_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "TopicLabeler", FakeTopicLabelerWithExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: updates.append((document_id, updated_info)) or True)
    monkeypatch.setattr(topic_tree_service_module, "get_metadata_store", lambda data_dir=None: store)

    async def resolve_document_label(document_id, doc_info):
        await asyncio.sleep(0)
        if document_id == "doc-2":
            return {
                "label": "劳动合同",
                "source_text": (doc_info or {}).get("summary_source", ""),
                "is_error": False,
                "source": "test_async_loop",
            }
        return {
            "label": None,
            "source_text": "",
            "is_error": False,
            "source": "test_async_loop",
        }

    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", resolve_document_label, raising=False)

    async def async_case():
        return TopicTreeService().build_topic_tree(force_rebuild=True)

    tree = asyncio.run(async_case())
    fallback_parent = next(topic for topic in tree["topics"] if topic["label"] == "兜底分类")

    assert [child["label"] for child in fallback_parent["children"]] == ["劳动合同"]
    assert fallback_parent["children"][0]["documents"][0]["document_id"] == "doc-2"
    assert any(
        document_id == "doc-2"
        and payload["topic_label"] == "劳动合同"
        and payload["topic_path"] == ["兜底分类", "劳动合同"]
        and "classification_result" not in payload
        for document_id, payload in updates
    )
    assert "topic_tree" in store.saved


def test_build_topic_tree_all_excluded_documents_builds_fallback_only_without_null_sync(monkeypatch):
    updates = []
    store = FakeStore()

    def documents():
        return [
            {"id": "doc-1", "filename": "labor-contract.docx", "file_type": ".docx", "classification_result": None, "created_at_iso": "2026-04-01T10:00:00"},
            {"id": "doc-2", "filename": "broken.docx", "file_type": ".docx", "classification_result": None, "created_at_iso": "2026-04-02T10:00:00"},
        ]

    class FakeTopicClusteringAllExcluded:
        def __init__(self, *args, **kwargs):
            pass

        def build_document_vectors(self, docs):
            return (
                [],
                [
                    {**docs[0], "exclude_reason": "missing_vector"},
                    {**docs[1], "exclude_reason": "unusable_content"},
                ],
            )

        def cluster_documents(self, docs, level):
            raise AssertionError("cluster_documents should not be called when all documents are excluded")

    monkeypatch.setattr(topic_tree_service_module, "get_all_documents", documents)
    monkeypatch.setattr(
        topic_tree_service_module,
        "get_document_content_record",
        lambda document_id: {
            "doc-1": {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
            "doc-2": {"preview_content": "Word处理失败: Package not found at '/tmp/broken.docx'"},
        }[document_id],
    )
    monkeypatch.setattr(topic_tree_service_module, "list_document_segments", lambda document_id: [])
    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringAllExcluded, raising=False)
    monkeypatch.setattr(topic_tree_service_module, "update_document_info", lambda document_id, updated_info: updates.append((document_id, updated_info)) or True)
    monkeypatch.setattr(topic_tree_service_module, "get_metadata_store", lambda data_dir=None: store)

    def resolve_document_label(document_id, doc_info):
        if document_id == "doc-1":
            return {
                "label": "劳动合同",
                "source_text": (doc_info or {}).get("summary_source", ""),
                "is_error": False,
                "source": "test_all_excluded",
            }
        return {
            "label": "Error",
            "source_text": "",
            "is_error": True,
            "source": "test_all_excluded",
        }

    monkeypatch.setattr(topic_tree_service_module, "resolve_document_label", resolve_document_label, raising=False)

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)
    parent_labels = [topic["label"] for topic in tree["topics"]]

    assert tree["clustered_documents"] == 0
    assert tree["excluded_documents"] == 2
    assert parent_labels == ["兜底分类", "异常文档"]
    assert any(
        document_id == "doc-1"
        and payload["topic_label"] == "劳动合同"
        and payload["topic_path"] == ["兜底分类", "劳动合同"]
        and "classification_result" not in payload
        for document_id, payload in updates
    )
    assert any(
        document_id == "doc-2"
        and payload["topic_label"] == "Error"
        and payload["topic_path"] == ["异常文档", "Error"]
        and "classification_result" not in payload
        for document_id, payload in updates
    )
    assert "topic_tree" in store.saved


def test_build_topic_tree_keeps_semantic_topics_and_fallback_topics_separate(monkeypatch):
    store = _patch_common_dependencies(monkeypatch)

    class FakeTopicClusteringMixed(FakeTopicClustering):
        def build_document_vectors(self, documents):
            return (
                [
                    {**documents[0], "vector": [1.0, 0.0]},
                    {**documents[1], "vector": [2.0, 0.0]},
                ],
                [{**documents[2], "exclude_reason": "missing_vector"}],
            )

    monkeypatch.setattr(topic_tree_service_module, "TopicClustering", FakeTopicClusteringMixed, raising=False)
    monkeypatch.setattr(
        topic_tree_service_module,
        "resolve_document_label",
        lambda document_id, doc_info: {
            "label": "供应商比价",
            "source_text": "供应商报价对比与合同条件评估。",
            "is_error": False,
            "source": "llm",
        },
        raising=False,
    )

    tree = TopicTreeService().build_topic_tree(force_rebuild=True)

    labels = [topic["label"] for topic in tree["topics"]]
    assert "财务治理" in labels
    assert "兜底分类" in labels
    assert "异常文档" not in labels

    semantic_parent = next(topic for topic in tree["topics"] if topic["label"] == "财务治理")
    fallback_parent = next(topic for topic in tree["topics"] if topic["label"] == "兜底分类")

    semantic_doc_ids = {
        document["document_id"]
        for child in semantic_parent["children"]
        for document in child["documents"]
    }
    fallback_doc_ids = {
        document["document_id"]
        for child in fallback_parent["children"]
        for document in child["documents"]
    }

    assert semantic_doc_ids == {"doc-1", "doc-2"}
    assert fallback_doc_ids == {"doc-3"}
    assert semantic_doc_ids.isdisjoint(fallback_doc_ids)
    assert store.saved["topic_tree"]["excluded_documents"] == 1


def test_topic_tree_api_returns_service_payload(monkeypatch):
    mock_get_topic_tree = Mock(
        return_value={
            "generated_at": "2026-03-24T10:00:00",
            "schema_version": 3,
            "total_documents": 2,
            "clustered_documents": 2,
            "excluded_documents": 0,
            "topics": [{"topic_id": "topic-1", "label": "财务治理", "children": []}],
        }
    )
    monkeypatch.setattr(classification_api.classification_service, "get_topic_tree", mock_get_topic_tree)

    body = asyncio.run(classification_api.get_topic_tree())

    assert body["code"] == 200
    assert body["data"]["schema_version"] == 3
    assert body["data"]["total_documents"] == 2
    mock_get_topic_tree.assert_called_once()
