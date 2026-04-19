import asyncio
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.repositories.document_repository import DocumentRepository  # noqa: E402
from app.services.document_audit_service import DocumentAuditService  # noqa: E402


class FakeLightRAGClient:
    async def health(self):
        return {"status": "healthy"}


class FakeLocalEmbeddingRuntime:
    async def health(self):
        return {"status": "healthy", "model": "bge-m3"}


def test_document_audit_reports_metadata_files_and_runtime_health(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    classified_dir = tmp_path / "classified_docs"
    data_dir.mkdir()
    doc_dir.mkdir()
    classified_dir.mkdir()

    tracked_file = doc_dir / "tracked.pdf"
    tracked_file.write_bytes(b"%PDF-1.4")
    untracked_file = classified_dir / "untracked.docx"
    untracked_file.write_bytes(b"docx")
    (data_dir / "legacy.json").write_text(
        '{"id":"legacy","filename":"legacy.pdf","filepath":"/missing/legacy.pdf"}',
        encoding="utf-8",
    )

    repo = DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir)
    repo.upsert(
        {
            "id": "doc-1",
            "filename": "tracked.pdf",
            "filepath": str(tracked_file),
            "file_type": ".pdf",
            "ingest_status": "ready",
        }
    )
    repo.upsert(
        {
            "id": "doc-2",
            "filename": "queued.pdf",
            "filepath": str(doc_dir / "missing.pdf"),
            "file_type": ".pdf",
            "ingest_status": "queued",
        }
    )

    service = DocumentAuditService(
        document_repository=repo,
        data_dir=data_dir,
        doc_dir=doc_dir,
        classified_dir=classified_dir,
        lightrag_client=FakeLightRAGClient(),
        local_embedding_runtime=FakeLocalEmbeddingRuntime(),
    )

    payload = asyncio.run(service.audit())

    assert payload["sqlite_documents"] == 2
    assert payload["local_files"] == 2
    assert payload["legacy_json_documents"] == 1
    assert payload["pending_ingest_documents"] == 1
    assert payload["missing_file_documents"] == 1
    assert payload["untracked_local_files"] == [str(untracked_file.resolve())]
    assert payload["lightrag"]["status"] == "healthy"
    assert payload["local_embedding"]["status"] == "healthy"


def test_document_audit_handles_lightrag_failure(tmp_path: Path):
    class BrokenLightRAGClient:
        async def health(self):
            raise RuntimeError("connection refused")

    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    data_dir.mkdir()
    doc_dir.mkdir()

    service = DocumentAuditService(
        document_repository=DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir),
        data_dir=data_dir,
        doc_dir=doc_dir,
        classified_dir=tmp_path / "classified_docs",
        lightrag_client=BrokenLightRAGClient(),
        local_embedding_runtime=FakeLocalEmbeddingRuntime(),
    )

    payload = asyncio.run(service.audit())

    assert payload["lightrag"]["status"] == "unhealthy"
    assert "connection refused" in payload["lightrag"]["detail"]


def test_document_audit_handles_local_embedding_failure(tmp_path: Path):
    class BrokenLocalEmbeddingRuntime:
        async def health(self):
            raise RuntimeError("8011 connection refused")

    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    data_dir.mkdir()
    doc_dir.mkdir()

    service = DocumentAuditService(
        document_repository=DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir),
        data_dir=data_dir,
        doc_dir=doc_dir,
        classified_dir=tmp_path / "classified_docs",
        lightrag_client=FakeLightRAGClient(),
        local_embedding_runtime=BrokenLocalEmbeddingRuntime(),
    )

    payload = asyncio.run(service.audit())

    assert payload["local_embedding"]["status"] == "unhealthy"
    assert "8011 connection refused" in payload["local_embedding"]["detail"]


def test_register_local_only_documents_imports_untracked_business_files_but_skips_test_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    classified_dir = tmp_path / "classified_docs"
    (doc_dir / "test").mkdir(parents=True)
    (doc_dir / "pdf").mkdir(parents=True)
    classified_dir.mkdir()
    data_dir.mkdir()

    business_file = classified_dir / "contract.docx"
    business_file.write_bytes(b"docx")
    ignored_test_file = doc_dir / "test" / "fixture.txt"
    ignored_test_file.write_text("fixture", encoding="utf-8")

    repo = DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir)
    service = DocumentAuditService(
        document_repository=repo,
        data_dir=data_dir,
        doc_dir=doc_dir,
        classified_dir=classified_dir,
        lightrag_client=FakeLightRAGClient(),
        local_embedding_runtime=FakeLocalEmbeddingRuntime(),
    )

    created = service.register_local_only_documents()
    docs = repo.list_all()

    assert created == 1
    assert len(docs) == 1
    assert docs[0]["filename"] == "contract.docx"
    assert docs[0]["ingest_status"] == "local_only"
    assert docs[0]["filepath"] == str(business_file.resolve())


def test_register_local_only_documents_skips_lightrag_enqueued_shadow_files(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    (doc_dir / "__enqueued__").mkdir(parents=True)
    data_dir.mkdir()

    mirrored_file = doc_dir / "__enqueued__" / "remote-doc.pdf"
    mirrored_file.write_bytes(b"%PDF-1.4")

    repo = DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir)
    service = DocumentAuditService(
        document_repository=repo,
        data_dir=data_dir,
        doc_dir=doc_dir,
        classified_dir=tmp_path / "classified_docs",
        lightrag_client=FakeLightRAGClient(),
        local_embedding_runtime=FakeLocalEmbeddingRuntime(),
    )

    created = service.register_local_only_documents()

    assert created == 0
    assert repo.list_all() == []


def test_register_local_only_documents_removes_existing_duplicate_local_only_records(tmp_path: Path):
    data_dir = tmp_path / "data"
    doc_dir = tmp_path / "doc"
    (doc_dir / "__enqueued__").mkdir(parents=True)
    data_dir.mkdir()

    mirrored_file = doc_dir / "__enqueued__" / "remote-doc.pdf"
    mirrored_file.write_bytes(b"%PDF-1.4")

    repo = DocumentRepository(db_path=tmp_path / "docagent.db", data_dir=data_dir)
    repo.upsert(
        {
            "id": "tracked-1",
            "filename": "remote-doc.pdf",
            "filepath": str(tmp_path / "elsewhere" / "source.pdf"),
            "file_type": ".pdf",
            "ingest_status": "failed",
            "lightrag_doc_id": "doc-remote-doc",
            "lightrag_track_id": "track-1",
        }
    )
    repo.upsert(
        {
            "id": "local-only-1",
            "filename": "remote-doc.pdf",
            "filepath": str(mirrored_file.resolve()),
            "file_type": ".pdf",
            "ingest_status": "local_only",
        }
    )

    service = DocumentAuditService(
        document_repository=repo,
        data_dir=data_dir,
        doc_dir=doc_dir,
        classified_dir=tmp_path / "classified_docs",
        lightrag_client=FakeLightRAGClient(),
        local_embedding_runtime=FakeLocalEmbeddingRuntime(),
    )

    created = service.register_local_only_documents()
    docs = {item["id"]: item for item in repo.list_all()}

    assert created == 0
    assert "tracked-1" in docs
    assert "local-only-1" not in docs
