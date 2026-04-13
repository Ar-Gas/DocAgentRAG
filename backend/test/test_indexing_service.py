import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.indexing_service as indexing_service_module  # noqa: E402
from app.services.indexing_service import IndexingService  # noqa: E402


class FakeCollection:
    def __init__(self, existing_ids=None):
        self.existing_ids = list(existing_ids or [])
        self.get_calls = []
        self.deleted_ids = []
        self.add_calls = []

    def get(self, where=None, include=None):
        self.get_calls.append({"where": where, "include": include})
        return {"ids": list(self.existing_ids)}

    def delete(self, ids=None):
        self.deleted_ids.append(list(ids or []))

    def add(self, documents, metadatas, ids):
        self.add_calls.append(
            {
                "documents": list(documents),
                "metadatas": list(metadatas),
                "ids": list(ids),
            }
        )


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
