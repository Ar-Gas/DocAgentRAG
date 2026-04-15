import os
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.storage as storage  # noqa: E402
from app.infra import metadata_store as metadata_store_module  # noqa: E402


@pytest.fixture()
def isolated_storage(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    chroma_dir = tmp_path / "chromadb"
    data_dir.mkdir()
    doc_dir.mkdir()
    chroma_dir.mkdir()

    metadata_store_module._metadata_stores.clear()
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "DOC_DIR", doc_dir)
    monkeypatch.setattr(storage, "CHROMA_DB_PATH", chroma_dir)
    monkeypatch.setattr(storage, "_chroma_client", None)
    monkeypatch.setattr(storage, "_chroma_collection", None)
    yield storage
    metadata_store_module._metadata_stores.clear()


def test_document_info_and_classification_roundtrip(isolated_storage):
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

    assert isolated_storage.save_document_info(doc_info) is True
    assert isolated_storage.get_document_info("doc-1")["filename"] == "report.pdf"

    assert isolated_storage.save_classification_result("doc-1", "财务") is True
    assert isolated_storage.get_classification_result("doc-1") == "财务"


def test_get_all_documents_and_filter_by_classification(isolated_storage):
    isolated_storage.save_document_info({"id": "doc-1", "filename": "a.pdf", "filepath": "/tmp/a.pdf", "classification_result": "财务"})
    isolated_storage.save_document_info({"id": "doc-2", "filename": "b.docx", "filepath": "/tmp/b.docx", "classification_result": "法务"})
    isolated_storage.save_document_info({"id": "doc-3", "filename": "c.txt", "filepath": "/tmp/c.txt", "classification_result": "财务"})

    all_docs = isolated_storage.get_all_documents()
    assert {item["id"] for item in all_docs} == {"doc-1", "doc-2", "doc-3"}

    finance_docs = isolated_storage.get_documents_by_classification("财务")
    assert {item["id"] for item in finance_docs} == {"doc-1", "doc-3"}


def test_init_chroma_client_returns_client_and_collection(monkeypatch, isolated_storage):
    client = Mock()
    collection = Mock()
    client.get_or_create_collection.return_value = collection

    monkeypatch.setattr(storage, "doubao_multimodal_embed", lambda text: None)
    monkeypatch.setattr(storage, "PersistentClient", lambda path: client)
    monkeypatch.setattr(
        storage.embedding_functions,
        "SentenceTransformerEmbeddingFunction",
        lambda model_name: object(),
    )

    initialized_client, initialized_collection = isolated_storage.init_chroma_client()

    assert initialized_client is client
    assert initialized_collection is collection


def test_save_document_summary_for_classification_persists_content(monkeypatch, isolated_storage, tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("项目会议纪要", encoding="utf-8")
    legacy_tree_update = Mock()
    monkeypatch.setattr(
        storage,
        "update_classification_tree_after_add",
        legacy_tree_update,
        raising=False,
    )

    document_id, doc_info = isolated_storage.save_document_summary_for_classification(
        str(source),
        full_content="项目会议纪要",
        parser_name="text",
    )

    assert document_id
    assert doc_info["filename"] == "notes.txt"
    assert isolated_storage.get_document_content_record(document_id)["full_content"] == "项目会议纪要"
    legacy_tree_update.assert_not_called()


def test_save_document_to_chroma_persists_segments(monkeypatch, isolated_storage, tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("第一句。第二句。第三句。", encoding="utf-8")
    isolated_storage.save_document_info(
        {
            "id": "doc-1",
            "filename": "notes.txt",
            "filepath": str(source),
            "file_type": ".txt",
            "created_at_iso": "2024-03-09T00:00:00",
        }
    )

    collection = Mock()
    monkeypatch.setattr(storage, "get_chroma_collection", lambda: collection)
    monkeypatch.setattr(storage, "split_text_into_chunks", lambda text: ["第一句。", "第二句。", "第三句。"])

    assert isolated_storage.save_document_to_chroma(str(source), document_id="doc-1", use_refiner=False) is True
    assert collection.add.called is True
    segments = isolated_storage.list_document_segments("doc-1")
    assert len(segments) == 3


def test_retrieve_from_chroma_and_delete_document(monkeypatch, isolated_storage):
    isolated_storage.save_document_info({"id": "doc-1", "filename": "notes.txt", "filepath": "/tmp/notes.txt"})
    isolated_storage.save_document_content_record("doc-1", "全文", preview_content="摘要")

    collection = Mock()
    collection.query.return_value = {"documents": [["Result 1"]]}
    collection.get.return_value = {"ids": ["doc-1_chunk_0"]}
    monkeypatch.setattr(storage, "get_chroma_collection", lambda: collection)
    legacy_tree_delete = Mock()
    monkeypatch.setattr(
        storage,
        "update_classification_tree_after_delete",
        legacy_tree_delete,
        raising=False,
    )

    assert isolated_storage.retrieve_from_chroma("query") == {"documents": [["Result 1"]]}
    assert isolated_storage.delete_document("doc-1") is True
    collection.delete.assert_called_once_with(ids=["doc-1_chunk_0"])
    assert isolated_storage.get_document_info("doc-1") is None
    legacy_tree_delete.assert_not_called()


def test_update_document_info_and_split_text_into_chunks(isolated_storage):
    isolated_storage.save_document_info({"id": "doc-1", "filename": "old.txt", "filepath": "/tmp/old.txt"})

    assert isolated_storage.update_document_info("doc-1", {"filename": "new.txt"}) is True
    updated = isolated_storage.get_document_info("doc-1")
    assert updated["filename"] == "new.txt"
    assert updated.get("updated_at")

    chunks = isolated_storage.split_text_into_chunks("这是第一句。这是第二句！这是第三句？", max_length=6, min_length=2)
    assert len(chunks) == 3
    assert chunks[0].endswith("。")

    english_chunks = isolated_storage.split_text_into_chunks("This is one. This is two! This is three?", max_length=18, min_length=5)
    assert len(english_chunks) >= 2


def test_resolve_document_filepath_repairs_metadata_when_file_has_been_moved(monkeypatch, isolated_storage, tmp_path: Path):
    classified_root = tmp_path / "classified_docs" / "学术论文-教育"
    classified_root.mkdir(parents=True)
    repaired_file = classified_root / "589ab58b599b4bd0aa4f381857a55b67.pdf"
    repaired_file.write_text("pdf placeholder", encoding="utf-8")

    missing_original = tmp_path / "doc" / "pdf" / "589ab58b599b4bd0aa4f381857a55b67.pdf"
    isolated_storage.save_document_info(
        {
            "id": "doc-1",
            "filename": "指导教师名册.pdf",
            "filepath": str(missing_original),
            "file_type": ".pdf",
        }
    )

    monkeypatch.setattr(storage, "BASE_DIR", tmp_path)

    resolved = isolated_storage.resolve_document_filepath("doc-1")

    assert resolved == str(repaired_file.resolve())
    assert isolated_storage.get_document_info("doc-1")["filepath"] == str(repaired_file.resolve())


def test_resolve_document_filepath_handles_inaccessible_original_path(monkeypatch, isolated_storage, tmp_path: Path):
    test_root = tmp_path / "test" / "test_date"
    test_root.mkdir(parents=True)
    repaired_file = test_root / "sample.pdf"
    repaired_file.write_text("pdf placeholder", encoding="utf-8")

    inaccessible_path = "/root/autodl-tmp/DocAgentRAG/backend/test/test_date/sample.pdf"
    isolated_storage.save_document_info(
        {
            "id": "doc-2",
            "filename": "sample.pdf",
            "filepath": inaccessible_path,
            "file_type": ".pdf",
        }
    )

    monkeypatch.setattr(storage, "BASE_DIR", tmp_path)
    original_exists = Path.exists

    def fake_exists(path_obj):
        if str(path_obj) == inaccessible_path:
            raise PermissionError("permission denied")
        return original_exists(path_obj)

    monkeypatch.setattr(storage.Path, "exists", fake_exists, raising=False)

    resolved = isolated_storage.resolve_document_filepath("doc-2")

    assert resolved == str(repaired_file.resolve())
