import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.repositories.classification_table_repository import ClassificationTableRepository
from app.infra.repositories.document_artifact_repository import DocumentArtifactRepository
from app.infra.repositories.document_content_repository import DocumentContentRepository
from app.infra.repositories.document_repository import DocumentRepository
from app.infra.repositories.document_segment_repository import DocumentSegmentRepository
from app.infra.repositories.runtime_artifact_repository import RuntimeArtifactRepository


def test_repositories_roundtrip_document_related_records(tmp_path: Path):
    db_path = tmp_path / "docagent.db"
    data_dir = tmp_path / "data"

    documents = DocumentRepository(db_path=db_path, data_dir=data_dir)
    contents = DocumentContentRepository(db_path=db_path, data_dir=data_dir)
    segments = DocumentSegmentRepository(db_path=db_path, data_dir=data_dir)
    artifacts = DocumentArtifactRepository(db_path=db_path, data_dir=data_dir)

    assert documents.upsert(
        {
            "id": "doc-1",
            "filename": "spec.pdf",
            "filepath": "/tmp/spec.pdf",
            "file_type": ".pdf",
            "created_at_iso": "2026-04-16T00:00:00",
        }
    ) is True

    assert contents.save(
        "doc-1",
        full_content="full content",
        preview_content="preview",
        extraction_status="ready",
        parser_name="pdf",
    ) is True

    assert segments.replace(
        "doc-1",
        [
            {
                "segment_id": "doc-1#0",
                "segment_index": 0,
                "segment_type": "chunk",
                "content": "segment 0",
                "metadata": {"page": 1},
            }
        ],
    ) is True

    artifact_id = artifacts.upsert(
        "doc-1",
        "reader_blocks",
        {"blocks": [{"block_id": "doc-1:block-v1:0"}]},
    )

    assert documents.get("doc-1")["filename"] == "spec.pdf"
    assert contents.get("doc-1")["full_content"] == "full content"
    assert segments.list("doc-1")[0]["metadata"]["page"] == 1
    assert artifact_id == "doc-1:reader_blocks"
    assert artifacts.get("doc-1", "reader_blocks")["payload"]["blocks"][0]["block_id"] == "doc-1:block-v1:0"


def test_repositories_roundtrip_runtime_artifacts_and_classification_tables(tmp_path: Path):
    db_path = tmp_path / "docagent.db"
    data_dir = tmp_path / "data"

    runtime_artifacts = RuntimeArtifactRepository(db_path=db_path, data_dir=data_dir)
    classification_tables = ClassificationTableRepository(db_path=db_path, data_dir=data_dir)

    assert runtime_artifacts.save("topic_tree", {"schema_version": 2, "topics": []}) is True
    assert runtime_artifacts.load("topic_tree") == {"schema_version": 2, "topics": []}

    table_id = classification_tables.save(
        {
            "query": "项目周报",
            "title": "项目资料分组",
            "summary": "按主题分组",
            "rows": [{"label": "周报", "document_count": 3}],
        }
    )

    assert table_id
    assert classification_tables.get(table_id)["query"] == "项目周报"
    assert classification_tables.list(limit=10)[0]["id"] == table_id
