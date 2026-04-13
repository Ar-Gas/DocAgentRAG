import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.indexing_service as indexing_service_module  # noqa: E402
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
