from pathlib import Path

from app.infra.metadata_store import DocumentMetadataStore


def test_metadata_store_persists_document_processing_stages(tmp_path: Path):
    store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)
    store.upsert_document(
        {
            "id": "doc-1",
            "filename": "budget.pdf",
            "filepath": str(tmp_path / "budget.pdf"),
            "file_type": ".pdf",
        }
    )

    store.upsert_document_stage(
        "doc-1",
        "content_extract",
        status="ready",
        error_code=None,
        error_message=None,
        retry_count=0,
        payload={"content_length": 128},
    )
    store.upsert_document_stage(
        "doc-1",
        "rag_ingest",
        status="failed",
        error_code="embedding_unready",
        error_message="local embedding server unavailable",
        retry_count=2,
        payload={"track_id": None},
    )

    stages = {row["stage_name"]: row for row in store.list_document_stages("doc-1")}

    assert stages["content_extract"]["status"] == "ready"
    assert stages["rag_ingest"]["error_code"] == "embedding_unready"
    assert stages["rag_ingest"]["retry_count"] == 2
    assert stages["rag_ingest"]["payload"]["track_id"] is None
