import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.metadata_store import DocumentMetadataStore


def test_document_content_segments_and_classification_tables_roundtrip(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )

    doc_info = {
        "id": "doc-1",
        "filename": "spec.pdf",
        "filepath": "/tmp/spec.pdf",
        "file_type": ".pdf",
        "created_at": 1710000000.0,
        "created_at_iso": "2024-03-09T00:00:00",
    }
    assert store.upsert_document(doc_info, mirror=False) is True

    assert store.save_document_content(
        "doc-1",
        full_content="full body",
        preview_content="preview",
        extraction_status="ready",
        parser_name="pdf",
        extraction_error=None,
    ) is True

    assert store.replace_document_segments(
        "doc-1",
        [
            {
                "segment_id": "doc-1#0",
                "segment_index": 0,
                "content": "segment 0",
                "segment_type": "chunk",
                "page_number": 1,
                "metadata": {"score": 0.9},
            },
            {
                "segment_id": "doc-1#1",
                "segment_index": 1,
                "content": "segment 1",
                "segment_type": "chunk",
                "page_number": 2,
                "metadata": {"score": 0.8},
            },
        ],
    ) is True

    saved_content = store.get_document_content("doc-1")
    assert saved_content["full_content"] == "full body"
    assert saved_content["preview_content"] == "preview"
    assert saved_content["parser_name"] == "pdf"

    segments = store.list_document_segments("doc-1")
    assert [segment["segment_id"] for segment in segments] == ["doc-1#0", "doc-1#1"]
    assert segments[0]["metadata"]["score"] == 0.9

    table_id = store.save_classification_table(
        {
            "query": "项目周报",
            "title": "项目资料分组",
            "summary": "按主题分组",
            "rows": [
                {"label": "周报", "document_count": 3, "keywords": ["进度", "风险"]},
            ],
        }
    )
    assert table_id

    saved_table = store.get_classification_table(table_id)
    assert saved_table["query"] == "项目周报"
    assert saved_table["rows"][0]["label"] == "周报"

    listed = store.list_classification_tables()
    assert [item["id"] for item in listed] == [table_id]


def test_delete_document_removes_related_content_and_segments(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    assert store.upsert_document(
        {
            "id": "doc-2",
            "filename": "draft.txt",
            "filepath": "/tmp/draft.txt",
            "file_type": ".txt",
        },
        mirror=False,
    )
    assert store.save_document_content(
        "doc-2",
        full_content="draft",
        preview_content="draft",
        extraction_status="ready",
        parser_name="text",
    )
    assert store.replace_document_segments(
        "doc-2",
        [{"segment_id": "doc-2#0", "segment_index": 0, "content": "draft"}],
    )

    assert store.delete_document("doc-2", mirror=False) is True
    assert store.get_document("doc-2") is None
    assert store.get_document_content("doc-2") is None
    assert store.list_document_segments("doc-2") == []


def test_block_artifact_helpers_upsert_single_reader_payload(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    assert store.upsert_document(
        {
            "id": "doc-1",
            "filename": "spec.docx",
            "filepath": "/tmp/spec.docx",
            "file_type": ".docx",
        },
        mirror=False,
    )

    artifact_id = store.upsert_document_artifact(
        "doc-1",
        "reader_blocks",
        {
            "index_version": "block-v1",
            "indexed_content_hash": "abc123",
            "blocks": [
                {
                    "block_id": "doc-1:block-v1:0",
                    "block_index": 0,
                    "block_type": "paragraph",
                    "heading_path": ["第一章 总则"],
                    "text": "示例正文",
                }
            ],
        },
    )

    saved = store.get_document_artifact("doc-1", "reader_blocks")

    assert artifact_id == "doc-1:reader_blocks"
    assert saved["artifact_id"] == "doc-1:reader_blocks"
    assert saved["payload"]["blocks"][0]["block_id"] == "doc-1:block-v1:0"


def test_get_document_artifact_prefers_deterministic_artifact_id(tmp_path: Path):
    store = DocumentMetadataStore(
        db_path=tmp_path / "docagent.db",
        data_dir=tmp_path / "data",
    )
    assert store.upsert_document(
        {
            "id": "doc-1",
            "filename": "spec.docx",
            "filepath": "/tmp/spec.docx",
            "file_type": ".docx",
        },
        mirror=False,
    )

    assert (
        store.upsert_document_artifact(
            "doc-1",
            "reader_blocks",
            {
                "source": "deterministic",
                "blocks": [{"block_id": "doc-1:block-v1:0"}],
            },
        )
        == "doc-1:reader_blocks"
    )
    assert (
        store.save_document_artifact(
            "doc-1",
            "reader_blocks",
            {
                "source": "manual",
                "blocks": [{"block_id": "manual:block"}],
            },
            artifact_id="doc-1:reader_blocks:manual-copy",
        )
        == "doc-1:reader_blocks:manual-copy"
    )

    saved = store.get_document_artifact("doc-1", "reader_blocks")

    assert saved["artifact_id"] == "doc-1:reader_blocks"
    assert saved["payload"]["source"] == "deterministic"
