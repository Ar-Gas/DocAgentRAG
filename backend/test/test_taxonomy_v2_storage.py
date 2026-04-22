import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.metadata_store import DocumentMetadataStore
from migrations import add_taxonomy_fields


def test_metadata_store_round_trips_taxonomy_v2_fields(tmp_path: Path):
    store = DocumentMetadataStore(db_path=tmp_path / "docagent.db", data_dir=tmp_path)

    store.upsert_document(
        {
            "id": "doc-1",
            "filename": "ops-manual.pdf",
            "filepath": str(tmp_path / "ops-manual.pdf"),
            "file_type": ".pdf",
            "classification_result": "运维手册",
            "classification_id": "tech.operations_manual",
            "classification_leaf_id": "tech.operations_manual",
            "classification_path": ["技术文档", "运维体系", "运维手册"],
            "classification_domain": "技术文档",
            "classification_score": 0.91,
            "classification_confidence": 0.91,
            "classification_source": "llm",
            "classification_review_status": "accepted",
            "classification_issue_code": None,
            "taxonomy_version": "taxonomy_v2",
        }
    )

    row = store.get_document("doc-1")

    assert row["classification_leaf_id"] == "tech.operations_manual"
    assert row["classification_domain"] == "技术文档"
    assert row["classification_confidence"] == 0.91
    assert row["taxonomy_version"] == "taxonomy_v2"


def test_add_taxonomy_fields_migration_adds_v2_columns(tmp_path: Path):
    db_path = tmp_path / "docagent.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                filename TEXT,
                classification_result TEXT,
                payload TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO documents (id, filename, classification_result, payload) VALUES (?, ?, ?, ?)",
            (
                "doc-1",
                "ops-manual.pdf",
                "运维手册",
                json.dumps({"id": "doc-1"}, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    summary = add_taxonomy_fields.migrate(db_path=db_path)

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
    finally:
        connection.close()

    assert summary["document_count"] == 1
    assert {
        "classification_leaf_id",
        "classification_domain",
        "classification_confidence",
        "taxonomy_version",
    }.issubset(columns)
