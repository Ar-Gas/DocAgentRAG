import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.repositories.document_repository import DocumentRepository  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402


class FakeLightRAGClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"status": "success", "track_id": "track-1", "message": "accepted"}
        self.error = error
        self.uploads = []
        self.reprocess_failed_calls = 0
        self.track_status_payload = {"track_id": "track-1", "documents": [], "total_count": 0, "status_summary": {}}

    async def upload_file(self, file_path: str, filename: str):
        self.uploads.append({"file_path": file_path, "filename": filename})
        if self.error:
            raise self.error
        return self.payload

    async def get_track_status(self, track_id: str):
        return self.track_status_payload

    async def reprocess_failed_documents(self):
        self.reprocess_failed_calls += 1
        return {"status": "reprocessing_started", "message": "reprocessing started", "track_id": ""}


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

    result = asyncio.run(service.process_pending_ingest(doc["id"]))
    stored = service._document_repository().get(doc["id"])

    assert result["ingest_status"] == "processing"
    assert result["lightrag_track_id"] == "old-track"
    assert result["ingest_error"] is None
    assert stored["ingest_status"] == "processing"
    assert stored["lightrag_track_id"] == "old-track"
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
