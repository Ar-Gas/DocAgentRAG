import os
import sys
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.classification_service as classification_service_module  # noqa: E402
import app.services.document_service as document_service_module  # noqa: E402
import app.services.indexing_service as indexing_service_module  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402
from app.services.indexing_service import IndexingService  # noqa: E402


class FakeCollection:
    def __init__(self, existing_ids=None):
        self.rows = {}
        for row_id in list(existing_ids or []):
            self.rows[row_id] = {
                "document": f"old-content:{row_id}",
                "metadata": {"document_id": row_id.split(":")[0], "block_id": row_id},
            }
        self.get_calls = []
        self.deleted_ids = []
        self.add_calls = []
        self.raise_on_add_once = None

    def get(self, where=None, include=None):
        self.get_calls.append({"where": where, "include": include})
        include = include or []
        document_id = (where or {}).get("document_id")
        ids = []
        documents = []
        metadatas = []
        for row_id, row in self.rows.items():
            if document_id and row["metadata"].get("document_id") != document_id:
                continue
            ids.append(row_id)
            documents.append(row["document"])
            metadatas.append(row["metadata"])

        payload = {"ids": ids}
        if "documents" in include:
            payload["documents"] = documents
        if "metadatas" in include:
            payload["metadatas"] = metadatas
        return payload

    def delete(self, ids=None):
        ids = list(ids or [])
        self.deleted_ids.append(ids)
        for row_id in ids:
            self.rows.pop(row_id, None)

    def add(self, documents, metadatas, ids):
        if self.raise_on_add_once:
            error = self.raise_on_add_once
            self.raise_on_add_once = None
            raise error
        self.add_calls.append(
            {
                "documents": list(documents),
                "metadatas": list(metadatas),
                "ids": list(ids),
            }
        )
        for row_id, document, metadata in zip(ids, documents, metadatas):
            self.rows[row_id] = {"document": document, "metadata": metadata}


def test_audit_block_index_detects_missing_rows_and_count_mismatch(monkeypatch):
    fake_collection = FakeCollection()
    fake_collection.rows = {
        "doc-2:block-v1:0": {
            "document": "合同审批",
            "metadata": {"document_id": "doc-2", "block_id": "doc-2:block-v1:0"},
        },
        "doc-2:block-v1:1": {
            "document": "合同盖章",
            "metadata": {"document_id": "doc-2", "block_id": "doc-2:block-v1:1"},
        },
        "ghost:block-v1:0": {
            "document": "ghost",
            "metadata": {"document_id": "ghost", "block_id": "ghost:block-v1:0"},
        },
    }

    monkeypatch.setattr(
        indexing_service_module,
        "get_all_documents",
        lambda: [
            {
                "id": "doc-1",
                "filename": "budget.pdf",
                "block_index_status": "ready",
                "block_count": 1,
            },
            {
                "id": "doc-2",
                "filename": "contract.docx",
                "block_index_status": "ready",
                "block_count": 3,
            },
            {
                "id": "doc-3",
                "filename": "notes.pdf",
                "block_index_status": "failed",
                "block_count": 0,
            },
        ],
    )
    monkeypatch.setattr(indexing_service_module, "get_block_collection", lambda: fake_collection)

    payload = IndexingService().audit_block_index()

    documents = {item["document_id"]: item for item in payload["documents"]}
    assert payload["rebuild_candidates"] == ["doc-1", "doc-2", "doc-3"]
    assert documents["doc-1"]["rebuild_reasons"] == ["missing_blocks"]
    assert documents["doc-1"]["actual_block_count"] == 0
    assert documents["doc-2"]["rebuild_reasons"] == ["block_count_mismatch"]
    assert documents["doc-2"]["actual_block_count"] == 2
    assert documents["doc-3"]["rebuild_reasons"] == ["status_failed", "missing_blocks"]
    assert payload["orphan_block_ids"] == ["ghost:block-v1:0"]


def test_cleanup_orphan_block_rows_deletes_only_unknown_documents(monkeypatch):
    fake_collection = FakeCollection()
    fake_collection.rows = {
        "doc-1:block-v1:0": {
            "document": "预算审批",
            "metadata": {"document_id": "doc-1", "block_id": "doc-1:block-v1:0"},
        },
        "ghost:block-v1:0": {
            "document": "ghost",
            "metadata": {"document_id": "ghost", "block_id": "ghost:block-v1:0"},
        },
        "missing-meta:block-v1:0": {
            "document": "ghost-meta",
            "metadata": {},
        },
    }

    monkeypatch.setattr(
        indexing_service_module,
        "get_all_documents",
        lambda: [{"id": "doc-1", "filename": "budget.pdf", "block_index_status": "ready"}],
    )
    monkeypatch.setattr(indexing_service_module, "get_block_collection", lambda: fake_collection)

    deleted_ids = IndexingService().cleanup_orphan_block_rows()

    assert deleted_ids == ["ghost:block-v1:0", "missing-meta:block-v1:0"]
    assert fake_collection.deleted_ids == [["ghost:block-v1:0", "missing-meta:block-v1:0"]]
    assert sorted(fake_collection.rows.keys()) == ["doc-1:block-v1:0"]


def test_index_document_replaces_old_block_entries_and_persists_reader_blocks(monkeypatch):
    fake_collection = FakeCollection(existing_ids=["doc-1:block-v0:0", "doc-1:block-v0:1"])
    captured_updates = []
    captured_artifacts = []

    monkeypatch.setattr(
        indexing_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filepath": "/tmp/doc-1.pdf",
            "file_type": ".pdf",
            "filename": "doc-1.pdf",
        },
    )
    monkeypatch.setattr(indexing_service_module, "get_block_collection", lambda: fake_collection)
    monkeypatch.setattr(
        indexing_service_module,
        "extract_structured_blocks",
        lambda filepath, document_id: {
            "index_version": "block-v1",
            "indexed_content_hash": "hash-abc123",
            "blocks": [
                {
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                    "block_type": "paragraph",
                    "heading_path": ["Section A"],
                    "page_number": 1,
                    "text": "hello block",
                }
            ],
        },
    )

    def fake_upsert_document_artifact(document_id, artifact_type, payload):
        captured_artifacts.append(
            {
                "document_id": document_id,
                "artifact_type": artifact_type,
                "payload": payload,
            }
        )
        return "doc-1:reader_blocks"

    monkeypatch.setattr(indexing_service_module, "upsert_document_artifact", fake_upsert_document_artifact)
    monkeypatch.setattr(
        indexing_service_module,
        "update_document_info",
        lambda document_id, updated_info: captured_updates.append((document_id, updated_info)) or True,
    )

    result = IndexingService().index_document("doc-1")

    assert fake_collection.deleted_ids == [["doc-1:block-v0:0", "doc-1:block-v0:1"]]
    assert len(fake_collection.add_calls) == 1
    assert fake_collection.add_calls[0]["ids"] == ["doc-1:block-v1:0"]
    assert result == {"document_id": "doc-1", "block_index_status": "ready"}

    assert len(captured_artifacts) == 1
    assert captured_artifacts[0]["artifact_type"] == IndexingService.READER_ARTIFACT_TYPE

    assert len(captured_updates) == 1
    update_payload = captured_updates[0][1]
    assert update_payload["indexed_content_hash"] == "hash-abc123"
    assert update_payload["block_count"] == 1
    assert update_payload["block_index_status"] == "ready"
    assert update_payload["last_indexed_at"]


def test_index_document_marks_metadata_failed_when_extraction_errors(monkeypatch):
    captured_updates = []

    monkeypatch.setattr(
        indexing_service_module,
        "get_document_info",
        lambda document_id: {"id": document_id, "filepath": "/tmp/doc-1.pdf", "file_type": ".pdf"},
    )
    monkeypatch.setattr(
        indexing_service_module,
        "extract_structured_blocks",
        lambda filepath, document_id: (_ for _ in ()).throw(RuntimeError("extract failed due to parser crash")),
    )
    monkeypatch.setattr(
        indexing_service_module,
        "update_document_info",
        lambda document_id, updated_info: captured_updates.append((document_id, updated_info)) or True,
    )

    result = IndexingService().index_document("doc-1")

    assert result["document_id"] == "doc-1"
    assert result["block_index_status"] == "failed"
    assert len(captured_updates) == 1
    update_payload = captured_updates[0][1]
    assert update_payload["block_index_status"] == "failed"
    assert "block_index_error" in update_payload
    assert update_payload["block_index_error"]
    assert "chunk_status" not in update_payload
    assert "chunk_info" not in update_payload


def test_index_document_restores_old_entries_when_add_fails_after_delete(monkeypatch):
    fake_collection = FakeCollection(existing_ids=["doc-1:block-v0:0", "doc-1:block-v0:1"])
    fake_collection.raise_on_add_once = RuntimeError("chroma add failed")
    captured_updates = []

    monkeypatch.setattr(
        indexing_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filepath": "/tmp/doc-1.pdf",
            "file_type": ".pdf",
            "filename": "doc-1.pdf",
        },
    )
    monkeypatch.setattr(indexing_service_module, "get_block_collection", lambda: fake_collection)
    monkeypatch.setattr(
        indexing_service_module,
        "extract_structured_blocks",
        lambda filepath, document_id: {
            "index_version": "block-v1",
            "indexed_content_hash": "hash-rollback-1",
            "blocks": [
                {
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                    "block_type": "paragraph",
                    "heading_path": [],
                    "page_number": 1,
                    "text": "new block",
                }
            ],
        },
    )
    monkeypatch.setattr(indexing_service_module, "upsert_document_artifact", lambda *args, **kwargs: "doc-1:reader_blocks")
    monkeypatch.setattr(
        indexing_service_module,
        "update_document_info",
        lambda document_id, updated_info: captured_updates.append((document_id, updated_info)) or True,
    )

    result = IndexingService().index_document("doc-1")

    assert fake_collection.deleted_ids[0] == ["doc-1:block-v0:0", "doc-1:block-v0:1"]
    assert sorted(fake_collection.rows.keys()) == ["doc-1:block-v0:0", "doc-1:block-v0:1"]
    assert result["block_index_status"] == "failed"
    assert len(captured_updates) == 1
    assert captured_updates[0][1]["block_index_status"] == "failed"


def test_rechunk_triggers_block_reindex_without_breaking_chunk_response(monkeypatch):
    expected_block_status = {
        "exists": True,
        "document_id": "doc-1",
        "block_index_status": "ready",
        "block_count": 3,
        "has_blocks": True,
        "chunk_count": 3,
        "has_chunks": True,
    }
    mock_indexing_service = Mock()

    monkeypatch.setattr(
        document_service_module,
        "re_chunk_document",
        lambda document_id, use_refiner: (_ for _ in ()).throw(AssertionError("legacy rechunk helper should not run")),
        raising=False,
    )
    monkeypatch.setattr(
        document_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "block_index_status": "ready",
            "block_count": 3,
            "index_version": "block-v1",
            "last_indexed_at": "2026-04-16T12:00:00",
            "block_index_error": None,
        },
    )
    fake_collection = Mock()
    fake_collection.get.return_value = {"ids": ["doc-1:block-v1:0", "doc-1:block-v1:1", "doc-1:block-v1:2"]}
    monkeypatch.setattr(document_service_module, "get_block_collection", lambda: fake_collection)

    service = DocumentService()
    service.get_document = Mock(return_value={"id": "doc-1"})
    service.indexing_service = mock_indexing_service
    mock_indexing_service.index_document.return_value = {"document_id": "doc-1", "block_index_status": "ready"}

    result = service.rechunk("doc-1", use_refiner=True)

    mock_indexing_service.index_document.assert_called_once_with("doc-1", force=True)
    assert result["document_id"] == expected_block_status["document_id"]
    assert result["block_index_status"] == expected_block_status["block_index_status"]
    assert result["block_count"] == expected_block_status["block_count"]
    assert result["has_blocks"] is True
    assert result["chunk_count"] == expected_block_status["chunk_count"]
    assert result["has_chunks"] is True


def test_upload_indexes_blocks_directly_without_legacy_chunk_write(monkeypatch, tmp_path):
    target_doc_dir = tmp_path / "doc"
    target_doc_dir.mkdir(parents=True)
    monkeypatch.setattr(document_service_module, "DOC_DIR", target_doc_dir)

    extracted = SimpleNamespace(success=True, content="第一段\n第二段", parser_name="text", error=None)
    service = DocumentService()
    service.extraction_service = Mock(extract=Mock(return_value=extracted))
    service.indexing_service = Mock(index_document=Mock(return_value={"document_id": "doc-1", "block_index_status": "ready"}))

    captured = {}

    def fake_save_summary(filepath, full_content=None, parser_name=None, display_filename=None):
        captured["filepath"] = filepath
        captured["full_content"] = full_content
        captured["parser_name"] = parser_name
        captured["display_filename"] = display_filename
        return (
            "doc-1",
            {
                "id": "doc-1",
                "filename": display_filename,
                "filepath": filepath,
                "file_type": ".txt",
                "created_at_iso": "2026-04-16T12:00:00",
            },
        )

    monkeypatch.setattr(document_service_module, "save_document_summary_for_classification", fake_save_summary)
    monkeypatch.setattr(
        document_service_module,
        "save_document_to_chroma",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy chunk write should not run")),
        raising=False,
    )
    monkeypatch.setattr(
        document_service_module,
        "get_document_info",
        lambda document_id: {
            "id": document_id,
            "filename": "notes.txt",
            "filepath": captured.get("filepath", ""),
            "file_type": ".txt",
            "created_at_iso": "2026-04-16T12:00:00",
            "block_index_status": "ready",
            "block_count": 2,
            "classification_result": "年度审计",
        },
    )
    cache = Mock()
    monkeypatch.setattr(document_service_module, "get_search_cache", lambda: cache)
    monkeypatch.setattr(classification_service_module, "ClassificationService", lambda: Mock(classify=Mock(return_value={})))

    result = service.upload("notes.txt", BytesIO("第一段\n第二段".encode("utf-8")))

    service.indexing_service.index_document.assert_called_once_with("doc-1", force=True)
    cache.invalidate_all.assert_called_once_with()
    assert captured["display_filename"] == "notes.txt"
    assert captured["full_content"] == "第一段\n第二段"
    assert result["id"] == "doc-1"
    assert result["block_index_status"] == "ready"
