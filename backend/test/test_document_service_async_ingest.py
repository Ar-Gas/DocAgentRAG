import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.repositories.document_repository import DocumentRepository  # noqa: E402
from app.services.extraction_service import ExtractionResult  # noqa: E402
import app.services.document_service as document_service_module  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402


class FakeLightRAGClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"status": "success", "track_id": "track-1", "message": "accepted"}
        self.error = error
        self.uploads = []
        self.reprocess_failed_calls = 0
        self.health_calls = 0
        self.health_payload = {"status": "healthy", "pipeline_busy": False}
        self.track_status_payload = {"track_id": "track-1", "documents": [], "total_count": 0, "status_summary": {}}
        self.track_status_by_id = {}
        self.track_status_calls = []
        self.paginated_payload = {
            "documents": [],
            "pagination": {"page": 1, "page_size": 100, "total_count": 0, "total_pages": 1, "has_next": False},
        }

    async def upload_file(self, file_path: str, filename: str):
        self.uploads.append({"file_path": file_path, "filename": filename})
        if self.error:
            raise self.error
        return self.payload

    async def get_track_status(self, track_id: str):
        self.track_status_calls.append(track_id)
        return self.track_status_by_id.get(track_id, self.track_status_payload)

    async def reprocess_failed_documents(self):
        self.reprocess_failed_calls += 1
        return {"status": "reprocessing_started", "message": "reprocessing started", "track_id": ""}

    async def health(self):
        self.health_calls += 1
        return self.health_payload

    async def list_documents_paginated(self, page: int = 1, page_size: int = 100):
        return self.paginated_payload


class FakeLocalEmbeddingRuntime:
    def __init__(self, error=None):
        self.error = error
        self.ensure_calls = 0

    async def ensure_ready(self):
        self.ensure_calls += 1
        if self.error:
            raise self.error
        return {"status": "healthy"}


def _service(tmp_path: Path, *, client=None, local_embedding_runtime=None) -> DocumentService:
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    return DocumentService(
        document_repository=DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir),
        data_dir=data_dir,
        doc_dir=doc_dir,
        lightrag_client=client or FakeLightRAGClient(),
        local_embedding_runtime=local_embedding_runtime or FakeLocalEmbeddingRuntime(),
        enqueue_background=False,
    )


class StubExtractionService:
    def __init__(self, content: str, parser_name: str = "pdf"):
        self.content = content
        self.parser_name = parser_name

    def extract(self, filepath):
        return ExtractionResult(
            success=True,
            content=self.content,
            parser_name=self.parser_name,
            preview_content=self.content[:1000],
            full_content_length=len(self.content),
            metadata={"filepath": filepath},
        )


def _configure_shard_thresholds(monkeypatch, *, threshold: int = 70, target: int = 60, hard: int = 60) -> None:
    monkeypatch.setattr(document_service_module, "LIGHTRAG_SHARD_CONTENT_THRESHOLD", threshold, raising=False)
    monkeypatch.setattr(document_service_module, "LIGHTRAG_SHARD_TARGET_SIZE", target, raising=False)
    monkeypatch.setattr(document_service_module, "LIGHTRAG_SHARD_HARD_LIMIT", hard, raising=False)


def _list_child_shards(service: DocumentService, parent_document_id: str):
    children = [
        item
        for item in (service._document_repository().list_all() or [])
        if item.get("parent_document_id") == parent_document_id
    ]
    return sorted(children, key=lambda item: int(item.get("shard_index") or 0))


def test_upload_persists_queued_document_without_running_parser(monkeypatch, tmp_path):
    service = _service(tmp_path)
    called = {"extract": 0, "index": 0}

    class ExplodingExtractionService:
        def extract(self, filepath):
            called["extract"] += 1
            raise AssertionError("upload request must not parse documents synchronously")

    class ExplodingIndexingService:
        def index_document(self, document_id, force=False):
            called["index"] += 1
            raise AssertionError("upload request must not index documents synchronously")

    service.extraction_service = ExplodingExtractionService()
    service.indexing_service = ExplodingIndexingService()

    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))

    assert doc["id"]
    assert doc["filename"] == "budget.pdf"
    assert doc["ingest_status"] == "queued"
    assert doc["ingest_error"] is None
    assert doc["lightrag_track_id"] is None
    assert Path(doc["filepath"]).exists()
    assert called == {"extract": 0, "index": 0}


def test_process_pending_ingest_stores_lightrag_track_id(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "track-42", "message": "accepted"})
    embedding_runtime = FakeLocalEmbeddingRuntime()
    service = _service(tmp_path, client=client, local_embedding_runtime=embedding_runtime)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))

    result = asyncio.run(service.process_pending_ingest(doc["id"]))
    refreshed = service.get_document(doc["id"])

    assert result["ingest_status"] == "processing"
    assert result["lightrag_track_id"] == "track-42"
    assert result["ingest_error"] is None
    assert refreshed["lightrag_track_id"] == "track-42"
    assert refreshed["ingest_status"] == "processing"
    assert embedding_runtime.ensure_calls == 1
    assert client.uploads == [{"file_path": doc["filepath"], "filename": "budget.pdf"}]


def test_process_local_index_persists_content_and_reader_blocks(tmp_path):
    service = _service(tmp_path)
    doc = service.upload("budget.txt", BytesIO("预算审批\n\n合同金额 100 万".encode("utf-8")))

    result = service.process_local_index(doc["id"])
    refreshed = service.get_document(doc["id"])
    content_record = service._content_repository().get(doc["id"])
    reader_payload = service.get_reader_payload(doc["id"], query="预算")

    assert result["local_index_status"] == "ready"
    assert refreshed["local_index_status"] == "ready"
    assert refreshed["extraction_status"] == "ready"
    assert refreshed["full_content_length"] > 0
    assert content_record["full_content"] == "预算审批\n\n合同金额 100 万"
    assert reader_payload["blocks"]
    assert reader_payload["total_matches"] == 1


def test_process_local_index_creates_shards_from_extracted_large_content(monkeypatch, tmp_path):
    _configure_shard_thresholds(monkeypatch)
    service = _service(tmp_path)
    service.extraction_service = StubExtractionService(
        "第一部分内容" * 6 + "\n\n" + "第二部分内容" * 6
    )
    doc = service.upload("manual.pdf", BytesIO(b"%PDF-1.4"))

    result = service.process_local_index(doc["id"])
    shards = _list_child_shards(service, doc["id"])

    assert result["shard_count"] == 2
    assert [item["filename"] for item in shards] == ["manual-1.pdf", "manual-2.pdf"]
    assert [item["shard_index"] for item in shards] == [1, 2]
    assert all(item["is_shard"] for item in shards)


def test_process_pending_ingest_uses_ordered_shards_instead_of_parent_upload(monkeypatch, tmp_path):
    _configure_shard_thresholds(monkeypatch)
    client = FakeLightRAGClient({"status": "success", "track_id": "track-42", "message": "accepted"})
    service = _service(tmp_path, client=client)
    service.extraction_service = StubExtractionService(
        "第一部分内容" * 6 + "\n\n" + "第二部分内容" * 6
    )
    doc = service.upload("manual.pdf", BytesIO(b"%PDF-1.4"))

    service.process_local_index(doc["id"])
    result = asyncio.run(service.process_pending_ingest(doc["id"]))

    assert result["filename"] == "manual.pdf"
    assert client.uploads == [
        {"file_path": doc["filepath"], "filename": "manual-1.pdf"},
        {"file_path": doc["filepath"], "filename": "manual-2.pdf"},
    ]


def test_get_document_aggregates_parent_status_from_shards(monkeypatch, tmp_path):
    _configure_shard_thresholds(monkeypatch)
    service = _service(tmp_path)
    service.extraction_service = StubExtractionService(
        "第一部分内容" * 6 + "\n\n" + "第二部分内容" * 6
    )
    doc = service.upload("manual.pdf", BytesIO(b"%PDF-1.4"))

    service.process_local_index(doc["id"])
    shards = _list_child_shards(service, doc["id"])
    service._update_ingest_status(shards[0]["id"], ingest_status="ready", ingest_error=None)
    service._update_ingest_status(shards[1]["id"], ingest_status="failed", ingest_error="second shard failed")

    parent = service.get_document(doc["id"])

    assert parent["ingest_status"] == "failed"
    assert parent["ingest_error"] == "second shard failed"


def test_retry_ingest_requeues_all_shards_for_sharded_parent(monkeypatch, tmp_path):
    _configure_shard_thresholds(monkeypatch)
    service = _service(tmp_path)
    service.extraction_service = StubExtractionService(
        "第一部分内容" * 6 + "\n\n" + "第二部分内容" * 6
    )
    doc = service.upload("manual.pdf", BytesIO(b"%PDF-1.4"))

    service.process_local_index(doc["id"])
    shards = _list_child_shards(service, doc["id"])
    service._update_document_info(
        shards[0]["id"],
        {
            "ingest_status": "failed",
            "ingest_error": "first shard failed",
            "lightrag_track_id": "track-1",
            "lightrag_doc_id": "doc-1",
        },
    )
    service._update_document_info(
        shards[1]["id"],
        {
            "ingest_status": "processing",
            "ingest_error": None,
            "lightrag_track_id": "track-2",
            "lightrag_doc_id": "doc-2",
        },
    )

    parent = service.retry_ingest(doc["id"])
    refreshed_shards = _list_child_shards(service, doc["id"])

    assert parent["ingest_status"] == "queued"
    assert parent["ingest_error"] is None
    assert [item["ingest_status"] for item in refreshed_shards] == ["queued", "queued"]
    assert [item["lightrag_track_id"] for item in refreshed_shards] == [None, None]
    assert [item["lightrag_doc_id"] for item in refreshed_shards] == [None, None]


def test_list_documents_hides_shard_children(monkeypatch, tmp_path):
    _configure_shard_thresholds(monkeypatch)
    service = _service(tmp_path)
    service.extraction_service = StubExtractionService(
        "第一部分内容" * 6 + "\n\n" + "第二部分内容" * 6
    )
    doc = service.upload("manual.pdf", BytesIO(b"%PDF-1.4"))

    service.process_local_index(doc["id"])
    page = service.list_documents(page=1, page_size=10)

    assert [item["filename"] for item in page["items"]] == ["manual.pdf"]


def test_list_documents_normalizes_legacy_status_fields_from_persisted_content(tmp_path):
    service = _service(tmp_path)
    repo = service._document_repository()
    legacy_file = tmp_path / "doc" / "legacy.txt"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text("可浏览正文", encoding="utf-8")
    repo.upsert(
        {
            "id": "legacy-1",
            "filename": "legacy.txt",
            "filepath": str(legacy_file),
            "file_type": ".txt",
            "ingest_status": None,
            "local_index_status": None,
            "preview_content": "",
        }
    )
    service._content_repository().save(
        "legacy-1",
        full_content="可浏览正文",
        preview_content="可浏览正文",
        extraction_status="ready",
        parser_name="txt",
    )

    page = service.list_documents(page=1, page_size=10)
    item = page["items"][0]

    assert item["ingest_status"] == "local_only"
    assert item["local_index_status"] == "ready"
    assert item["preview_content"] == "可浏览正文"


def test_list_documents_does_not_sync_remote_ingest_status(tmp_path):
    client = FakeLightRAGClient()
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))
    service._update_ingest_status(
        doc["id"],
        ingest_status="processing",
        ingest_error=None,
        lightrag_track_id="track-processing",
        lightrag_doc_id="remote-doc-1",
        last_status_sync_at="2026-04-20T00:00:00",
    )

    page = service.list_documents(page=1, page_size=10)

    assert page["items"][0]["ingest_status"] == "processing"
    assert client.track_status_calls == []


def test_list_documents_skips_expensive_file_repair_for_missing_paths(monkeypatch, tmp_path):
    service = _service(tmp_path)
    repo = service._document_repository()
    missing_path = tmp_path / "missing" / "ghost.pdf"
    repo.upsert(
        {
            "id": "ghost-1",
            "filename": "ghost.pdf",
            "filepath": str(missing_path),
            "file_type": ".pdf",
            "ingest_status": "local_only",
            "local_index_status": "ready",
            "preview_content": "ghost",
        }
    )

    def explode(*args, **kwargs):
        raise AssertionError("list_documents must not trigger repository-wide file repair")

    monkeypatch.setattr(document_service_module, "_enrich_document_file_state", explode)

    page = service.list_documents(page=1, page_size=10)

    assert page["items"][0]["id"] == "ghost-1"
    assert page["items"][0]["file_available"] is False


def test_sync_pending_remote_status_preserves_original_sync_time_for_stale_detection(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_by_id["track-old"] = {
        "track_id": "track-old",
        "documents": [
            {
                "id": "remote-doc-1",
                "status": "pending",
                "error_msg": "",
            }
        ],
    }
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))
    original_sync_time = "2026-04-20T00:00:00"
    service._update_ingest_status(
        doc["id"],
        ingest_status="queued",
        ingest_error=None,
        lightrag_track_id="track-old",
        lightrag_doc_id="remote-doc-1",
        last_status_sync_at=original_sync_time,
    )

    synced = service.get_document(doc["id"])

    assert synced["ingest_status"] == "queued"
    assert synced["last_status_sync_at"] == original_sync_time


def test_sync_processing_remote_status_preserves_processing_start_time_for_stale_detection(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_by_id["track-processing"] = {
        "track_id": "track-processing",
        "documents": [
            {
                "id": "remote-doc-1",
                "status": "processing",
                "error_msg": "",
                "metadata": {"processing_start_time": 1776692925},
            }
        ],
    }
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))
    original_sync_time = "2026-04-20T00:00:00"
    service._update_ingest_status(
        doc["id"],
        ingest_status="processing",
        ingest_error=None,
        lightrag_track_id="track-processing",
        lightrag_doc_id="remote-doc-1",
        last_status_sync_at=original_sync_time,
    )

    synced = service.get_document(doc["id"])

    assert synced["ingest_status"] == "processing"
    assert synced["last_status_sync_at"] == original_sync_time


def test_process_local_index_records_failure_without_breaking_lightrag_ingest(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "track-42", "message": "accepted"})
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))

    class BrokenExtractionService:
        def extract(self, filepath):
            raise RuntimeError("parser exploded")

    service.extraction_service = BrokenExtractionService()

    index_result = service.process_local_index(doc["id"])
    ingest_result = asyncio.run(service.process_pending_ingest(doc["id"]))

    assert index_result["local_index_status"] == "failed"
    assert "parser exploded" in index_result["local_index_error"]
    assert ingest_result["ingest_status"] == "processing"
    assert ingest_result["lightrag_track_id"] == "track-42"
    assert client.uploads == [{"file_path": doc["filepath"], "filename": "budget.pdf"}]


def test_process_pending_ingest_fails_fast_when_local_embedding_unavailable(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "track-42", "message": "accepted"})
    embedding_runtime = FakeLocalEmbeddingRuntime(error=RuntimeError("local embedding server unavailable"))
    service = _service(tmp_path, client=client, local_embedding_runtime=embedding_runtime)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))

    result = asyncio.run(service.process_pending_ingest(doc["id"]))

    assert result["ingest_status"] == "failed"
    assert "local embedding server unavailable" in result["ingest_error"]
    assert embedding_runtime.ensure_calls == 1
    assert client.uploads == []


def test_process_pending_ingest_records_failure_without_deleting_file(tmp_path):
    class UploadError(Exception):
        pass

    client = FakeLightRAGClient(error=UploadError("LightRAG returned 400: MinerU未安装"))
    service = _service(tmp_path, client=client)
    doc = service.upload("scan.pdf", BytesIO(b"%PDF-1.4"))

    result = asyncio.run(service.process_pending_ingest(doc["id"]))
    refreshed = service.get_document(doc["id"])

    assert result["ingest_status"] == "failed"
    assert "MinerU未安装" in result["ingest_error"]
    assert Path(doc["filepath"]).exists()
    assert refreshed["ingest_status"] == "failed"
    assert "MinerU未安装" in refreshed["ingest_error"]


def test_process_pending_ingest_reprocesses_duplicate_failed_lightrag_document(tmp_path):
    client = FakeLightRAGClient(
        {"status": "duplicated", "track_id": "old-track", "message": "File already exists"}
    )
    client.track_status_by_id["old-track"] = {
        "track_id": "old-track",
        "documents": [
            {
                "id": "dup-remote-doc",
                "status": "failed",
                "error_msg": "Content already exists. Original doc_id: original-doc-1",
                "metadata": {
                    "is_duplicate": True,
                    "original_doc_id": "original-doc-1",
                    "original_track_id": "original-track-1",
                },
            }
        ],
    }
    client.track_status_by_id["original-track-1"] = {
        "track_id": "original-track-1",
        "documents": [
            {
                "id": "original-doc-1",
                "status": "failed",
                "error_msg": "old embedding failure",
            }
        ],
    }
    service = _service(tmp_path, client=client)
    doc = service.upload("scan.pdf", BytesIO(b"%PDF-1.4"))

    result = asyncio.run(service.process_pending_ingest(doc["id"]))
    stored = service._document_repository().get(doc["id"])

    assert result["ingest_status"] == "processing"
    assert result["lightrag_track_id"] == "original-track-1"
    assert result["lightrag_doc_id"] == "original-doc-1"
    assert result["ingest_error"] is None
    assert stored["ingest_status"] == "processing"
    assert stored["lightrag_track_id"] == "original-track-1"
    assert stored["lightrag_doc_id"] == "original-doc-1"
    assert client.reprocess_failed_calls == 1


def test_retry_ingest_requeues_failed_document(tmp_path):
    client = FakeLightRAGClient(error=RuntimeError("temporary failure"))
    service = _service(tmp_path, client=client)
    doc = service.upload("scan.pdf", BytesIO(b"%PDF-1.4"))
    asyncio.run(service.process_pending_ingest(doc["id"]))

    service.lightrag_client = FakeLightRAGClient({"status": "success", "track_id": "retry-track"})
    retry_payload = service.retry_ingest(doc["id"])
    result = asyncio.run(service.process_pending_ingest(doc["id"]))

    assert retry_payload["ingest_status"] == "queued"
    assert retry_payload["ingest_error"] is None
    assert result["ingest_status"] == "processing"
    assert result["lightrag_track_id"] == "retry-track"


def test_retry_ingest_clears_stale_lightrag_track_state(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "old-track"})
    client.track_status_payload = {
        "track_id": "old-track",
        "documents": [
            {
                "id": "old-remote-doc",
                "status": "failed",
                "error_msg": "old embedding failure",
            }
        ],
    }
    service = _service(tmp_path, client=client)
    doc = service.upload("scan.pdf", BytesIO(b"%PDF-1.4"))
    asyncio.run(service.process_pending_ingest(doc["id"]))
    service.get_document(doc["id"])

    retry_payload = service.retry_ingest(doc["id"])
    stored = service._document_repository().get(doc["id"])

    assert retry_payload["ingest_status"] == "queued"
    assert retry_payload["ingest_error"] is None
    assert retry_payload["lightrag_track_id"] is None
    assert retry_payload["lightrag_doc_id"] is None
    assert stored["lightrag_track_id"] is None
    assert stored["lightrag_doc_id"] is None


def test_process_pending_ingest_accepts_local_only_documents(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "local-track"})
    service = _service(tmp_path, client=client)
    repo = service._document_repository()

    local_file = tmp_path / "doc" / "pdf" / "legacy.pdf"
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "local-1",
            "filename": "legacy.pdf",
            "filepath": str(local_file),
            "file_type": ".pdf",
            "ingest_status": "local_only",
        }
    )

    result = asyncio.run(service.process_pending_ingest("local-1"))

    assert result["ingest_status"] == "processing"
    assert result["lightrag_track_id"] == "local-track"
    assert client.uploads == [{"file_path": str(local_file), "filename": "legacy.pdf"}]


def test_upload_marks_lightrag_unsupported_types_as_local_only(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "image-track"})
    service = _service(tmp_path, client=client)

    doc = service.upload("diagram.png", BytesIO(b"\x89PNG\r\n\x1a\n"))

    assert doc["ingest_status"] == "local_only"
    assert doc["lightrag_track_id"] is None
    assert client.uploads == []


def test_process_pending_ingest_skips_lightrag_unsupported_local_only_documents(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "image-track"})
    service = _service(tmp_path, client=client)
    repo = service._document_repository()

    image_path = tmp_path / "doc" / "image" / "diagram.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    repo.upsert(
        {
            "id": "image-1",
            "filename": "diagram.png",
            "filepath": str(image_path),
            "file_type": ".png",
            "ingest_status": "local_only",
            "local_index_status": "ready",
        }
    )

    result = asyncio.run(service.process_pending_ingest("image-1"))

    assert result["ingest_status"] == "local_only"
    assert result.get("ingest_error") is None
    assert result.get("lightrag_track_id") is None
    assert client.uploads == []


def test_get_document_syncs_processing_ingest_status_from_lightrag_track_status(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "track-42", "message": "accepted"})
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "doc-remote-1",
                "status": "processed",
                "track_id": "track-42",
                "error_msg": None,
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"processed": 1},
    }
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))
    asyncio.run(service.process_pending_ingest(doc["id"]))

    synced = service.get_document(doc["id"])
    refreshed = service._document_repository().get(doc["id"])

    assert synced["ingest_status"] == "ready"
    assert synced["lightrag_doc_id"] == "doc-remote-1"
    assert synced["ingest_error"] is None
    assert refreshed["ingest_status"] == "ready"
    assert refreshed["lightrag_doc_id"] == "doc-remote-1"


def test_get_document_syncs_remote_pending_ingest_status_to_queued(tmp_path):
    client = FakeLightRAGClient({"status": "success", "track_id": "track-42", "message": "accepted"})
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "doc-remote-1",
                "status": "pending",
                "track_id": "track-42",
                "error_msg": None,
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"pending": 1},
    }
    service = _service(tmp_path, client=client)
    doc = service.upload("budget.pdf", BytesIO(b"%PDF-1.4"))
    asyncio.run(service.process_pending_ingest(doc["id"]))

    synced = service.get_document(doc["id"])
    refreshed = service._document_repository().get(doc["id"])

    assert synced["ingest_status"] == "queued"
    assert synced["lightrag_doc_id"] == "doc-remote-1"
    assert synced["ingest_error"] is None
    assert refreshed["ingest_status"] == "queued"


def test_get_document_syncs_duplicate_failed_ingest_to_original_pending_track(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_by_id["dup-track-1"] = {
        "track_id": "dup-track-1",
        "documents": [
            {
                "id": "dup-remote-doc",
                "status": "failed",
                "track_id": "dup-track-1",
                "error_msg": "Content already exists. Original doc_id: original-doc-1",
                "metadata": {
                    "is_duplicate": True,
                    "original_doc_id": "original-doc-1",
                    "original_track_id": "original-track-1",
                },
            }
        ],
        "total_count": 1,
        "status_summary": {"failed": 1},
    }
    client.track_status_by_id["original-track-1"] = {
        "track_id": "original-track-1",
        "documents": [
            {
                "id": "original-doc-1",
                "status": "pending",
                "track_id": "original-track-1",
                "error_msg": None,
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"pending": 1},
    }
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "failed",
            "ingest_error": "Content already exists. Original doc_id: original-doc-1",
            "lightrag_track_id": "dup-track-1",
            "lightrag_doc_id": "dup-remote-doc",
        }
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "queued"
    assert synced["ingest_error"] is None
    assert synced["lightrag_track_id"] == "original-track-1"
    assert synced["lightrag_doc_id"] == "original-doc-1"
    assert refreshed["ingest_status"] == "queued"
    assert refreshed["lightrag_track_id"] == "original-track-1"
    assert refreshed["lightrag_doc_id"] == "original-doc-1"


def test_get_document_normalizes_unsupported_lightrag_failures_to_local_only(tmp_path):
    client = FakeLightRAGClient()
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "image" / "diagram.webp"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"RIFF")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "diagram.webp",
            "filepath": str(file_path),
            "file_type": ".webp",
            "ingest_status": "failed",
            "ingest_error": "LightRAG returned 400: Unsupported file type. Supported types: ('.pdf')",
            "lightrag_track_id": "stale-track",
            "lightrag_doc_id": "stale-doc",
            "local_index_status": "ready",
        }
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "local_only"
    assert synced["ingest_error"] is None
    assert synced["lightrag_track_id"] is None
    assert synced["lightrag_doc_id"] is None
    assert refreshed["ingest_status"] == "local_only"
    assert refreshed["lightrag_track_id"] is None
    assert refreshed["lightrag_doc_id"] is None


def test_get_document_syncs_failed_ingest_status_to_ready_when_remote_processed(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "doc-remote-1",
                "status": "processed",
                "track_id": "track-42",
                "error_msg": None,
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"processed": 1},
    }
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "failed",
            "ingest_error": "old connection error",
            "lightrag_track_id": "track-42",
        }
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "ready"
    assert synced["ingest_error"] is None
    assert synced["lightrag_doc_id"] == "doc-remote-1"
    assert refreshed["ingest_status"] == "ready"
    assert refreshed["ingest_error"] is None


def test_get_document_syncs_failed_ingest_error_when_remote_failed_with_new_detail(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "doc-remote-1",
                "status": "failed",
                "track_id": "track-42",
                "error_msg": "LLM func: Worker execution timeout after 360s",
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"failed": 1},
    }
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "failed",
            "ingest_error": "RetryError[old]",
            "lightrag_track_id": "track-42",
        }
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "failed"
    assert synced["ingest_error"] == "LLM func: Worker execution timeout after 360s"
    assert synced["lightrag_doc_id"] == "doc-remote-1"
    assert refreshed["ingest_error"] == "LLM func: Worker execution timeout after 360s"


def test_get_document_downgrades_whitespace_extraction_failure_to_local_only_when_local_content_ready(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "error-remote-1",
                "status": "failed",
                "track_id": "track-42",
                "error_msg": "File content contains only whitespace characters",
                "file_path": "scanned.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"failed": 1},
    }
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "scanned.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "scanned.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "failed",
            "ingest_error": "File content contains only whitespace characters",
            "lightrag_track_id": "track-42",
            "lightrag_doc_id": "error-remote-1",
            "local_index_status": "ready",
            "extraction_status": "ready",
        }
    )
    service._content_repository().save(
        "doc-1",
        full_content="扫描文档正文",
        preview_content="扫描文档正文",
        extraction_status="ready",
        parser_name="pdf",
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "local_only"
    assert synced["ingest_error"] == "File content contains only whitespace characters"
    assert synced["lightrag_track_id"] == "track-42"
    assert synced["lightrag_doc_id"] == "error-remote-1"
    assert refreshed["ingest_status"] == "local_only"
    assert refreshed["ingest_error"] == "File content contains only whitespace characters"


def test_get_document_requests_reprocess_for_stale_remote_pending_when_pipeline_idle(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "doc-remote-1",
                "status": "pending",
                "track_id": "track-42",
                "error_msg": None,
                "metadata": {"processing_start_time": 1710000000},
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"pending": 1},
    }
    client.health_payload = {"status": "healthy", "pipeline_busy": False}
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "queued",
            "ingest_error": None,
            "lightrag_track_id": "track-42",
            "last_status_sync_at": "2026-04-19T00:00:00",
        }
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "queued"
    assert refreshed["ingest_status"] == "queued"
    assert client.health_calls == 1
    assert client.reprocess_failed_calls == 1


def test_get_document_does_not_reprocess_pending_when_pipeline_busy(tmp_path):
    client = FakeLightRAGClient()
    client.track_status_payload = {
        "track_id": "track-42",
        "documents": [
            {
                "id": "doc-remote-1",
                "status": "pending",
                "track_id": "track-42",
                "error_msg": None,
                "metadata": {"processing_start_time": 1710000000},
                "file_path": "budget.pdf",
            }
        ],
        "total_count": 1,
        "status_summary": {"pending": 1},
    }
    client.health_payload = {"status": "healthy", "pipeline_busy": True}
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "queued",
            "ingest_error": None,
            "lightrag_track_id": "track-42",
            "last_status_sync_at": "2026-04-19T00:00:00",
        }
    )

    synced = service.get_document("doc-1")
    refreshed = repo.get("doc-1")

    assert synced["ingest_status"] == "queued"
    assert refreshed["ingest_status"] == "queued"
    assert client.health_calls == 1
    assert client.reprocess_failed_calls == 0


def test_run_local_only_batch_import_throttles_concurrency_and_updates_status(tmp_path):
    class SlowLightRAGClient:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.uploaded_filenames = []

        async def upload_file(self, file_path: str, filename: str):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.uploaded_filenames.append(filename)
            await asyncio.sleep(0.01)
            self.active -= 1
            return {"status": "success", "track_id": f"track-{filename}"}

    client = SlowLightRAGClient()
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    doc_dir = tmp_path / "doc" / "pdf"
    doc_dir.mkdir(parents=True, exist_ok=True)

    for index in range(3):
        file_path = doc_dir / f"legacy-{index}.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        repo.upsert(
            {
                "id": f"local-{index}",
                "filename": file_path.name,
                "filepath": str(file_path),
                "file_type": ".pdf",
                "ingest_status": "local_only",
            }
        )

    ready_path = doc_dir / "ready.pdf"
    ready_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "ready-1",
            "filename": "ready.pdf",
            "filepath": str(ready_path),
            "file_type": ".pdf",
            "ingest_status": "ready",
        }
    )

    async def run_case():
        initial = service.start_local_only_batch_import(limit=3, concurrency=1, interval_seconds=0)
        assert initial["state"] == "running"
        assert initial["total"] == 3
        await service.wait_for_batch_import()
        return service.get_batch_import_status()

    final_status = asyncio.run(run_case())

    assert final_status["state"] == "completed"
    assert final_status["total"] == 3
    assert final_status["processed"] == 3
    assert final_status["succeeded"] == 3
    assert final_status["failed"] == 0
    assert final_status["current_document_ids"] == []
    assert client.max_active == 1
    assert client.uploaded_filenames == ["legacy-2.pdf", "legacy-1.pdf", "legacy-0.pdf"]

    refreshed_docs = {item["id"]: item for item in repo.list_all()}
    assert refreshed_docs["ready-1"]["ingest_status"] == "ready"
    assert refreshed_docs["local-0"]["ingest_status"] == "processing"
    assert refreshed_docs["local-1"]["ingest_status"] == "processing"
    assert refreshed_docs["local-2"]["ingest_status"] == "processing"


def test_recover_stale_lightrag_queue_triggers_when_pipeline_idle(tmp_path):
    client = FakeLightRAGClient()
    client.health_payload = {"status": "healthy", "pipeline_busy": False}
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "queued",
            "lightrag_track_id": "track-42",
        }
    )

    payload = service.recover_stale_lightrag_queue()

    assert payload["status"] == "triggered"
    assert payload["triggered"] is True
    assert payload["pending_documents"] == 1
    assert client.reprocess_failed_calls == 1


def test_recover_stale_lightrag_queue_skips_when_pipeline_busy(tmp_path):
    client = FakeLightRAGClient()
    client.health_payload = {"status": "healthy", "pipeline_busy": True}
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    file_path = tmp_path / "doc" / "pdf" / "budget.pdf"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"%PDF-1.4")
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(file_path),
            "file_type": ".pdf",
            "ingest_status": "queued",
            "lightrag_track_id": "track-42",
        }
    )

    payload = service.recover_stale_lightrag_queue()

    assert payload["status"] == "skipped"
    assert payload["triggered"] is False
    assert payload["pending_documents"] == 1
    assert payload["pipeline_busy"] is True
    assert client.reprocess_failed_calls == 0


def test_reconcile_missing_lightrag_documents_marks_orphaned_docs_local_only(tmp_path):
    client = FakeLightRAGClient()
    client.paginated_payload = {
        "documents": [
            {"id": "remote-1", "file_path": "present.pdf", "status": "processed"},
            {"id": "remote-2", "file_path": "queued.pdf", "status": "pending"},
        ],
        "pagination": {"page": 1, "page_size": 100, "total_count": 2, "total_pages": 1, "has_next": False},
    }
    service = _service(tmp_path, client=client)
    repo = service._document_repository()
    doc_dir = tmp_path / "doc" / "pdf"
    doc_dir.mkdir(parents=True, exist_ok=True)

    def create_doc(doc_id: str, filename: str, ingest_status: str, track_id: str | None = None) -> None:
        file_path = doc_dir / filename
        file_path.write_bytes(b"%PDF-1.4")
        repo.upsert(
            {
                "id": doc_id,
                "filename": filename,
                "filepath": str(file_path),
                "file_type": ".pdf",
                "ingest_status": ingest_status,
                "lightrag_track_id": track_id,
                "lightrag_doc_id": f"remote-{doc_id}" if track_id else None,
            }
        )

    create_doc("ready-present", "present.pdf", "ready", "track-present")
    create_doc("ready-missing", "missing.pdf", "ready", "track-missing")
    create_doc("processing-missing", "orphan.pdf", "processing")
    create_doc("queued-remote", "queued.pdf", "queued", "track-queued")

    payload = service.reconcile_missing_lightrag_documents(limit=10)
    refreshed = {item["id"]: item for item in repo.list_all()}

    assert payload["status"] == "completed"
    assert payload["remote_documents"] == 2
    assert payload["requeued_documents"] == 2
    assert payload["document_ids"] == ["ready-missing", "processing-missing"]
    assert refreshed["ready-present"]["ingest_status"] == "ready"
    assert refreshed["ready-present"]["lightrag_track_id"] == "track-present"
    assert refreshed["ready-missing"]["ingest_status"] == "local_only"
    assert refreshed["ready-missing"]["lightrag_track_id"] is None
    assert refreshed["ready-missing"]["lightrag_doc_id"] is None
    assert refreshed["processing-missing"]["ingest_status"] == "local_only"
    assert refreshed["processing-missing"]["lightrag_track_id"] is None
    assert refreshed["queued-remote"]["ingest_status"] == "queued"
    assert refreshed["queued-remote"]["lightrag_track_id"] == "track-queued"
