from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.database import connect_sqlite
from config import DATA_DIR


DEFAULT_DB_PATH = DATA_DIR / "docagent.db"
COLUMN_DEFINITIONS = {
    "classification_id": "TEXT DEFAULT NULL",
    "classification_path": "TEXT DEFAULT NULL",
    "classification_score": "REAL DEFAULT 0.0",
    "classification_source": "TEXT DEFAULT NULL",
    "classification_candidates": "TEXT DEFAULT NULL",
}


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is None:
        return Path(DEFAULT_DB_PATH)
    return Path(db_path)


def connect_database(db_path: str | Path | None = None):
    return connect_sqlite(resolve_db_path(db_path))


def _ensure_documents_table(connection) -> None:
    exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'documents'
        """
    ).fetchone()
    if not exists:
        raise RuntimeError("documents table does not exist")


def _list_document_columns(connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute("PRAGMA table_info(documents)").fetchall()
    }


def migrate(db_path: str | Path | None = None) -> dict[str, Any]:
    db_file = resolve_db_path(db_path)
    added_columns: list[str] = []

    with connect_database(db_file) as connection:
        _ensure_documents_table(connection)
        existing_columns = _list_document_columns(connection)

        for column_name, column_definition in COLUMN_DEFINITIONS.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                f"ALTER TABLE documents ADD COLUMN {column_name} {column_definition}"
            )
            added_columns.append(column_name)

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_doc_classification_id
            ON documents(classification_id)
            """
        )

        document_count = connection.execute(
            "SELECT COUNT(*) AS total FROM documents"
        ).fetchone()["total"]
        classified_count = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM documents
            WHERE classification_result IS NOT NULL
              AND TRIM(classification_result) != ''
            """
        ).fetchone()["total"]
        connection.commit()

    summary = {
        "db_path": str(db_file),
        "added_columns": added_columns,
        "document_count": int(document_count),
        "classified_count": int(classified_count),
    }

    print(
        "[taxonomy-migration] "
        f"db={summary['db_path']} "
        f"added_columns={len(added_columns)} "
        f"documents={summary['document_count']} "
        f"classification_result={summary['classified_count']}"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add taxonomy fields to documents table")
    parser.add_argument("--db-path", default=None, help="Override SQLite database path")
    args = parser.parse_args(argv)

    migrate(db_path=args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
