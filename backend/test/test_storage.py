import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra import file_utils as file_utils_module  # noqa: E402
from app.infra import metadata_store as metadata_store_module  # noqa: E402
from app.infra import vector_store as vector_store_module  # noqa: E402
from app.infra.repositories.document_content_repository import DocumentContentRepository  # noqa: E402
from app.infra.repositories.document_repository import DocumentRepository  # noqa: E402
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository  # noqa: E402
from app.services import document_vector_index_service as document_vector_index_service_module  # noqa: E402
from app.services.document_vector_index_service import DocumentVectorIndexService, split_text_into_chunks  # noqa: E402


@pytest.fixture()
def isolated_components(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    chroma_dir = tmp_path / "chromadb"
    data_dir.mkdir()
    doc_dir.mkdir()
    chroma_dir.mkdir()

    metadata_store_module._metadata_stores.clear()
    vector_store_module.reset_clients()

    document_repository = DocumentRepository(data_dir=data_dir)
    content_repository = DocumentContentRepository(data_dir=data_dir)
    segment_repository = DocumentSegmentRepository(data_dir=data_dir)
    vector_index_service = DocumentVectorIndexService(
        document_repository=document_repository,
        content_repository=content_repository,
        segment_repository=segment_repository,
    )

    yield SimpleNamespace(
        data_dir=data_dir,
        doc_dir=doc_dir,
        chroma_dir=chroma_dir,
        document_repository=document_repository,
        content_repository=content_repository,
        segment_repository=segment_repository,
        vector_index_service=vector_index_service,
    )

    metadata_store_module._metadata_stores.clear()
    vector_store_module.reset_clients()


def test_document_repository_and_classification_roundtrip(isolated_components):
    doc_info = {
        "id": "doc-1",
        "filename": "report.pdf",
        "filepath": "/tmp/report.pdf",
        "file_type": ".pdf",
        "preview_content": "摘要",
        "full_content_length": 12,
        "created_at": 1710000000.0,
        "created_at_iso": "2024-03-09T00:00:00",
    }

    assert isolated_components.document_repository.upsert(doc_info) is True
    assert isolated_components.document_repository.get("doc-1")["filename"] == "report.pdf"

    assert isolated_components.document_repository.save_classification_result("doc-1", "财务") is True
    assert isolated_components.document_repository.get("doc-1")["classification_result"] == "财务"


def test_document_repository_list_all_and_list_by_classification(isolated_components):
    isolated_components.document_repository.upsert(
        {"id": "doc-1", "filename": "a.pdf", "filepath": "/tmp/a.pdf", "classification_result": "财务"}
    )
    isolated_components.document_repository.upsert(
        {"id": "doc-2", "filename": "b.docx", "filepath": "/tmp/b.docx", "classification_result": "法务"}
    )
    isolated_components.document_repository.upsert(
        {"id": "doc-3", "filename": "c.txt", "filepath": "/tmp/c.txt", "classification_result": "财务"}
    )

    all_docs = isolated_components.document_repository.list_all()
    assert {item["id"] for item in all_docs} == {"doc-1", "doc-2", "doc-3"}

    finance_docs = isolated_components.document_repository.list_by_classification("财务")
    assert {item["id"] for item in finance_docs} == {"doc-1", "doc-3"}


def test_init_chroma_client_returns_client_and_collection(monkeypatch, isolated_components):
    client = Mock()
    collection = Mock()
    client.get_or_create_collection.return_value = collection

    vector_store_module.reset_clients()
    monkeypatch.setattr(vector_store_module, "doubao_multimodal_embed", lambda text: None)
    monkeypatch.setattr(vector_store_module, "PersistentClient", lambda path: client)
    monkeypatch.setattr(
        vector_store_module.embedding_functions,
        "SentenceTransformerEmbeddingFunction",
        lambda model_name: object(),
    )

    initialized_client, initialized_collection = vector_store_module.init_chroma_client(
        chroma_db_path=isolated_components.chroma_dir,
    )

    assert initialized_client is client
    assert initialized_collection is collection


def test_save_document_summary_for_classification_persists_content(isolated_components, tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("项目会议纪要", encoding="utf-8")
    bridge_calls = []

    document_id, doc_info = isolated_components.vector_index_service.save_document_summary_for_classification(
        str(source),
        full_content="项目会议纪要",
        parser_name="text",
        classification_bridge_add=lambda payload: bridge_calls.append(payload),
    )

    assert document_id
    assert doc_info["filename"] == "notes.txt"
    assert bridge_calls and bridge_calls[0]["id"] == document_id
    assert isolated_components.content_repository.get(document_id)["full_content"] == "项目会议纪要"


def test_save_document_to_chroma_persists_segments(monkeypatch, isolated_components, tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("第一句。第二句。第三句。", encoding="utf-8")
    isolated_components.document_repository.upsert(
        {
            "id": "doc-1",
            "filename": "notes.txt",
            "filepath": str(source),
            "file_type": ".txt",
            "created_at_iso": "2024-03-09T00:00:00",
        }
    )

    collection = Mock()
    monkeypatch.setattr(
        document_vector_index_service_module,
        "split_text_into_chunks",
        lambda text, max_length=0, min_length=0: ["第一句。", "第二句。", "第三句。"],
    )

    assert (
        isolated_components.vector_index_service.save_document_to_chroma(
            str(source),
            document_id="doc-1",
            use_refiner=False,
            collection=collection,
            update_document_info=isolated_components.document_repository.update,
        )
        is True
    )
    assert collection.add.called is True
    segments = isolated_components.segment_repository.list("doc-1")
    assert len(segments) == 3


def test_retrieve_from_chroma_and_delete_document(isolated_components):
    isolated_components.document_repository.upsert({"id": "doc-1", "filename": "notes.txt", "filepath": "/tmp/notes.txt"})
    isolated_components.content_repository.save("doc-1", full_content="全文", preview_content="摘要")

    collection = Mock()
    collection.query.return_value = {"documents": [["Result 1"]]}
    collection.get.return_value = {"ids": ["doc-1_chunk_0"]}

    assert isolated_components.vector_index_service.retrieve_from_chroma("query", collection=collection) == {
        "documents": [["Result 1"]]
    }
    assert (
        isolated_components.vector_index_service.delete_document(
            "doc-1",
            collection=collection,
            delete_document_record=isolated_components.document_repository.delete,
            classification_bridge_delete=lambda document_id: None,
        )
        is True
    )
    collection.delete.assert_called_once_with(ids=["doc-1_chunk_0"])
    assert isolated_components.document_repository.get("doc-1") is None


def test_split_text_into_chunks():
    chunks = split_text_into_chunks("这是第一句。这是第二句！这是第三句？", max_length=6, min_length=2)
    assert len(chunks) == 3
    assert chunks[0].endswith("。")

    english_chunks = split_text_into_chunks("This is one. This is two! This is three?", max_length=18, min_length=5)
    assert len(english_chunks) >= 2


def test_resolve_document_filepath_repairs_metadata_when_file_has_been_moved(isolated_components, tmp_path: Path):
    classified_root = tmp_path / "classified_docs" / "学术论文-教育"
    classified_root.mkdir(parents=True)
    repaired_file = classified_root / "589ab58b599b4bd0aa4f381857a55b67.pdf"
    repaired_file.write_text("pdf placeholder", encoding="utf-8")

    missing_original = tmp_path / "doc" / "pdf" / "589ab58b599b4bd0aa4f381857a55b67.pdf"
    isolated_components.document_repository.upsert(
        {
            "id": "doc-1",
            "filename": "指导教师名册.pdf",
            "filepath": str(missing_original),
            "file_type": ".pdf",
        }
    )

    resolved = file_utils_module.resolve_document_filepath(
        "doc-1",
        base_dir=tmp_path,
        doc_dir=isolated_components.doc_dir,
        get_document_info=isolated_components.document_repository.get,
        update_document_info=isolated_components.document_repository.update,
    )

    assert resolved == str(repaired_file.resolve())
    assert isolated_components.document_repository.get("doc-1")["filepath"] == str(repaired_file.resolve())


def test_resolve_document_filepath_handles_inaccessible_original_path(monkeypatch, isolated_components, tmp_path: Path):
    test_root = tmp_path / "test" / "test_date"
    test_root.mkdir(parents=True)
    repaired_file = test_root / "sample.pdf"
    repaired_file.write_text("pdf placeholder", encoding="utf-8")

    inaccessible_path = "/root/autodl-tmp/DocAgentRAG/backend/test/test_date/sample.pdf"
    isolated_components.document_repository.upsert(
        {
            "id": "doc-2",
            "filename": "sample.pdf",
            "filepath": inaccessible_path,
            "file_type": ".pdf",
        }
    )

    original_exists = Path.exists

    def fake_exists(path_obj):
        if str(path_obj) == inaccessible_path:
            raise PermissionError("permission denied")
        return original_exists(path_obj)

    monkeypatch.setattr(file_utils_module.Path, "exists", fake_exists, raising=False)

    resolved = file_utils_module.resolve_document_filepath(
        "doc-2",
        base_dir=tmp_path,
        doc_dir=isolated_components.doc_dir,
        get_document_info=isolated_components.document_repository.get,
        update_document_info=isolated_components.document_repository.update,
    )

    assert resolved == str(repaired_file.resolve())
