import json
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.migrations import add_taxonomy_fields, backfill_taxonomy  # noqa: E402


def _create_documents_table(db_path: Path) -> None:
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
        connection.commit()
    finally:
        connection.close()


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def test_add_taxonomy_fields_adds_columns_index_and_summary(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "docagent.db"
    _create_documents_table(db_path)

    with _connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO documents (id, filename, classification_result, payload) VALUES (?, ?, ?, ?)",
            [
                ("doc-1", "offer.docx", "Offer审批", json.dumps({"id": "doc-1", "filename": "offer.docx", "classification_result": "Offer审批"}, ensure_ascii=False)),
                ("doc-2", "empty.docx", None, json.dumps({"id": "doc-2", "filename": "empty.docx"}, ensure_ascii=False)),
            ],
        )
        connection.commit()

    first = add_taxonomy_fields.migrate(db_path=db_path)
    second = add_taxonomy_fields.migrate(db_path=db_path)

    with _connect(db_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(documents)").fetchall()
        }

    assert {
        "classification_id",
        "classification_path",
        "classification_score",
        "classification_source",
        "classification_candidates",
    }.issubset(columns)
    assert "idx_doc_classification_id" in indexes
    assert first["document_count"] == 2
    assert first["classified_count"] == 1
    assert second["added_columns"] == []

    output = capsys.readouterr().out
    assert "documents=2" in output
    assert "classification_result=1" in output


def test_backfill_taxonomy_updates_missing_fields_from_keyword_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "docagent.db"
    _create_documents_table(db_path)
    add_taxonomy_fields.migrate(db_path=db_path)

    with _connect(db_path) as connection:
        connection.executemany(
                """
                INSERT INTO documents (
                    id, filename, classification_result, classification_id, payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("doc-1", "offer.docx", "Offer审批", None, json.dumps({"id": "doc-1", "filename": "offer.docx", "classification_result": "Offer审批"}, ensure_ascii=False)),
                    ("doc-2", "random.docx", "未知分类", None, json.dumps({"id": "doc-2", "filename": "random.docx", "classification_result": "未知分类"}, ensure_ascii=False)),
                    ("doc-3", "filled.docx", "Offer审批", "existing.id", json.dumps({"id": "doc-3", "filename": "filled.docx", "classification_result": "Offer审批", "classification_id": "existing.id"}, ensure_ascii=False)),
                ],
            )
        connection.commit()

    def fake_search_by_keyword(text: str, top_k: int = 10, filename_text: str = ""):
        del top_k, filename_text
        if text == "Offer审批":
            return [
                (
                    {
                        "id": "hr.offer_approval",
                        "path": ["人力资源", "招聘管理", "Offer审批"],
                        "label": "Offer审批",
                    },
                    0.82,
                ),
                (
                    {
                        "id": "hr.recruitment",
                        "path": ["人力资源", "招聘管理", "招聘总览"],
                        "label": "招聘总览",
                    },
                    0.41,
                ),
            ]
        return []

    monkeypatch.setattr(backfill_taxonomy, "search_by_keyword", fake_search_by_keyword)

    stats = backfill_taxonomy.backfill(db_path=db_path)

    with _connect(db_path) as connection:
        row1 = connection.execute(
            """
            SELECT classification_id, classification_path, classification_score,
                   classification_source, classification_candidates, payload
            FROM documents
            WHERE id = 'doc-1'
            """
        ).fetchone()
        row2 = connection.execute(
            "SELECT classification_id FROM documents WHERE id = 'doc-2'"
        ).fetchone()
        row3 = connection.execute(
            "SELECT classification_id FROM documents WHERE id = 'doc-3'"
        ).fetchone()

    assert stats["processed"] == 2
    assert stats["updated"] == 1
    assert row1["classification_id"] == "hr.offer_approval"
    assert json.loads(row1["classification_path"]) == ["人力资源", "招聘管理", "Offer审批"]
    assert row1["classification_score"] == 0.82
    assert row1["classification_source"] == "keyword"
    assert json.loads(row1["classification_candidates"]) == [
        "hr.offer_approval",
        "hr.recruitment",
    ]
    payload = json.loads(row1["payload"])
    assert payload["classification_id"] == "hr.offer_approval"
    assert payload["classification_path"] == ["人力资源", "招聘管理", "Offer审批"]
    assert payload["classification_score"] == 0.82
    assert payload["classification_source"] == "keyword"
    assert payload["classification_candidates"] == ["hr.offer_approval", "hr.recruitment"]
    assert row2["classification_id"] is None
    assert row3["classification_id"] == "existing.id"


def test_backfill_taxonomy_prints_progress_every_10_and_is_idempotent(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "docagent.db"
    _create_documents_table(db_path)
    add_taxonomy_fields.migrate(db_path=db_path)

    with _connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO documents (id, filename, classification_result, payload) VALUES (?, ?, ?, ?)",
            [
                (
                    f"doc-{index}",
                    f"doc-{index}.docx",
                    "Offer审批",
                    json.dumps({"id": f"doc-{index}", "filename": f"doc-{index}.docx", "classification_result": "Offer审批"}, ensure_ascii=False),
                )
                for index in range(11)
            ],
        )
        connection.commit()

    monkeypatch.setattr(
        backfill_taxonomy,
        "search_by_keyword",
        lambda text, top_k=10, filename_text="": [
            (
                {
                    "id": "hr.offer_approval",
                    "path": ["人力资源", "招聘管理", "Offer审批"],
                    "label": "Offer审批",
                },
                0.9,
            )
        ]
        if text == "Offer审批"
        else [],
    )

    first = backfill_taxonomy.backfill(db_path=db_path)
    output = capsys.readouterr().out
    second = backfill_taxonomy.backfill(db_path=db_path)

    assert first["processed"] == 11
    assert first["updated"] == 11
    assert "10/11" in output
    assert second["processed"] == 0
    assert second["updated"] == 0
