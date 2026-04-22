from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.domain.taxonomy.internet_enterprise_taxonomy import search_by_keyword

from .add_taxonomy_fields import connect_database, resolve_db_path

PSEUDO_CLASSIFICATION_IDS = {
    "system.pending_sync",
    "admin.unclassified",
}
PSEUDO_CLASSIFICATION_LABELS = {
    "待本地索引同步",
    "待人工确认",
}
PSEUDO_CLASSIFICATION_SOURCES = {
    "pending_sync",
    "pending_local_content",
}
STALE_LOCAL_INDEX_ERRORS = (
    "Embedding dimension 1024 does not match collection dimensionality 384",
)
LIGHTRAG_SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".mdx", ".pdf", ".docx", ".pptx", ".xlsx", ".rtf",
    ".odt", ".tex", ".epub", ".html", ".htm", ".csv", ".json", ".xml",
    ".yaml", ".yml", ".log", ".conf", ".ini", ".properties", ".sql",
    ".bat", ".sh", ".c", ".h", ".cpp", ".hpp", ".py", ".java", ".js",
    ".ts", ".swift", ".go", ".rb", ".php", ".css", ".scss", ".less",
}
LIGHTRAG_UNSUPPORTED_ERROR_MARKER = "unsupported file type"


def _load_pending_documents(connection) -> list[Any]:
    return connection.execute(
        """
        SELECT id, filename, classification_result, payload
        FROM documents
        WHERE classification_result IS NOT NULL
          AND TRIM(classification_result) != ''
          AND (classification_id IS NULL OR TRIM(classification_id) = '')
        ORDER BY id
        """
    ).fetchall()


def _has_column(connection, table_name: str, column_name: str) -> bool:
    return any(
        row["name"] == column_name
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    )


def _has_table(connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return bool(row)


def _merge_payload(row: Any, *, label: dict[str, Any], score: float, candidate_ids: list[str]) -> str | None:
    raw_payload = row["payload"] if "payload" in row.keys() else None
    if raw_payload is None:
        return None

    try:
        payload = json.loads(raw_payload) if raw_payload else {}
    except Exception:
        payload = {}

    payload.update(
        {
            "classification_id": label.get("id"),
            "classification_path": list(label.get("path") or []),
            "classification_score": round(float(score), 4),
            "classification_source": "keyword",
            "classification_candidates": candidate_ids,
        }
    )
    return json.dumps(payload, ensure_ascii=False)


def _load_payload(raw_payload: str | None) -> dict[str, Any]:
    if raw_payload is None:
        return {}
    try:
        payload = json.loads(raw_payload) if raw_payload else {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _cleanup_pseudo_classifications(connection) -> int:
    has_payload = _has_column(connection, "documents", "payload")
    rows = connection.execute(
        """
        SELECT id, classification_result, classification_id, classification_source, payload
        FROM documents
        """
    ).fetchall()
    cleaned = 0

    for row in rows:
        classification_result = str(row["classification_result"] or "").strip()
        classification_id = str(row["classification_id"] or "").strip()
        classification_source = str(row["classification_source"] or "").strip()
        should_clean = (
            classification_result in PSEUDO_CLASSIFICATION_LABELS
            or classification_id in PSEUDO_CLASSIFICATION_IDS
            or classification_source in PSEUDO_CLASSIFICATION_SOURCES
        )
        if not should_clean:
            continue

        update_payload = None
        if has_payload:
            try:
                update_payload = json.loads(row["payload"] or "{}")
            except Exception:
                update_payload = {}
            for key in [
                "classification_result",
                "classification_id",
                "classification_path",
                "classification_score",
                "classification_source",
                "classification_candidates",
            ]:
                update_payload[key] = None if key != "classification_path" else []
            update_payload["classification_review_status"] = "none"
            update_payload["classification_issue_code"] = "pending_local_content"

        parameters = ["none", "pending_local_content"]
        update_sql = """
            UPDATE documents
            SET classification_result = NULL,
                classification_id = NULL,
                classification_path = NULL,
                classification_score = 0.0,
                classification_source = NULL,
                classification_candidates = NULL,
                classification_review_status = ?,
                classification_issue_code = ?
        """
        if has_payload:
            update_sql += ", payload = ?"
            parameters.append(json.dumps(update_payload, ensure_ascii=False))
        update_sql += " WHERE id = ?"
        parameters.append(row["id"])
        connection.execute(update_sql, tuple(parameters))
        cleaned += 1

    return cleaned


def _clear_ready_pending_local_content(connection) -> int:
    if not _has_table(connection, "document_contents"):
        return 0
    has_payload = _has_column(connection, "documents", "payload")
    rows = connection.execute(
        """
        SELECT d.id, d.payload
        FROM documents AS d
        JOIN document_contents AS dc ON dc.document_id = d.id
        WHERE COALESCE(TRIM(d.classification_issue_code), '') = 'pending_local_content'
          AND LOWER(COALESCE(dc.extraction_status, '')) = 'ready'
          AND (
                COALESCE(TRIM(dc.full_content), '') != ''
             OR COALESCE(TRIM(dc.preview_content), '') != ''
          )
        """
    ).fetchall()
    cleared = 0
    for row in rows:
        update_payload = _load_payload(row["payload"]) if has_payload else None
        if update_payload is not None:
            update_payload["classification_review_status"] = "needs_review"
            update_payload["classification_issue_code"] = "no_match"

        parameters = ["needs_review", "no_match"]
        update_sql = """
            UPDATE documents
            SET classification_review_status = ?,
                classification_issue_code = ?
        """
        if has_payload:
            update_sql += ", payload = ?"
            parameters.append(json.dumps(update_payload, ensure_ascii=False))
        update_sql += " WHERE id = ?"
        parameters.append(row["id"])
        connection.execute(update_sql, tuple(parameters))
        cleared += 1
    return cleared


def _normalize_document_status_fields(connection) -> int:
    if not _has_table(connection, "document_contents"):
        return 0
    has_payload = _has_column(connection, "documents", "payload")
    file_type_expr = "d.file_type" if _has_column(connection, "documents", "file_type") else "NULL AS file_type"
    rows = connection.execute(
        f"""
        SELECT d.id, {file_type_expr},
               d.ingest_status, d.ingest_error,
               d.lightrag_track_id, d.lightrag_doc_id,
               d.local_index_status, d.local_index_error, d.payload,
               dc.extraction_status AS content_extraction_status,
               dc.full_content, dc.preview_content
        FROM documents AS d
        LEFT JOIN document_contents AS dc ON dc.document_id = d.id
        """
    ).fetchall()
    normalized = 0

    for row in rows:
        payload = _load_payload(row["payload"]) if has_payload else {}
        current_file_type = str(row["file_type"] or payload.get("file_type") or "").strip().lower()
        current_ingest = str(row["ingest_status"] or payload.get("ingest_status") or "").strip().lower()
        current_ingest_error = row["ingest_error"]
        if current_ingest_error is None and payload:
            current_ingest_error = payload.get("ingest_error")
        current_local_index = str(row["local_index_status"] or payload.get("local_index_status") or "").strip().lower()
        current_local_index_error = row["local_index_error"]
        if current_local_index_error is None and payload:
            current_local_index_error = payload.get("local_index_error")
        extraction_status = str(
            row["content_extraction_status"] or payload.get("extraction_status") or ""
        ).strip().lower()
        has_content = bool(
            str(row["full_content"] or "").strip() or str(row["preview_content"] or "").strip()
        )

        updates: dict[str, Any] = {}
        if not current_ingest:
            updates["ingest_status"] = "local_only"
        if (
            current_ingest == "failed"
            and (
                (
                    current_file_type
                    and current_file_type not in LIGHTRAG_SUPPORTED_EXTENSIONS
                )
                or LIGHTRAG_UNSUPPORTED_ERROR_MARKER in str(current_ingest_error or "").strip().lower()
            )
        ):
            updates["ingest_status"] = "local_only"
            updates["ingest_error"] = None
            updates["lightrag_track_id"] = None
            updates["lightrag_doc_id"] = None
        if has_content and extraction_status == "ready":
            if current_local_index in {"", "processing", "queued"}:
                updates["local_index_status"] = "ready"
            if current_local_index_error in STALE_LOCAL_INDEX_ERRORS:
                updates["local_index_error"] = None

        if not updates:
            continue

        if has_payload:
            payload.update(updates)
        parameters = [
            updates.get("ingest_status", row["ingest_status"]),
            updates.get("ingest_error", row["ingest_error"]),
            updates.get("lightrag_track_id", row["lightrag_track_id"]),
            updates.get("lightrag_doc_id", row["lightrag_doc_id"]),
            updates.get("local_index_status", row["local_index_status"]),
            updates.get("local_index_error", row["local_index_error"]),
        ]
        update_sql = """
            UPDATE documents
            SET ingest_status = ?,
                ingest_error = ?,
                lightrag_track_id = ?,
                lightrag_doc_id = ?,
                local_index_status = ?,
                local_index_error = ?
        """
        if has_payload:
            update_sql += ", payload = ?"
            parameters.append(json.dumps(payload, ensure_ascii=False))
        update_sql += " WHERE id = ?"
        parameters.append(row["id"])
        connection.execute(update_sql, tuple(parameters))
        normalized += 1

    return normalized


def _clear_forced_keyword_classifications(connection) -> int:
    has_payload = _has_column(connection, "documents", "payload")
    rows = connection.execute(
        """
        SELECT id, payload
        FROM documents
        WHERE COALESCE(TRIM(classification_source), '') = 'keyword_forced'
        """
    ).fetchall()
    cleared = 0

    for row in rows:
        update_payload = _load_payload(row["payload"]) if has_payload else None
        if update_payload is not None:
            for key in [
                "classification_result",
                "classification_id",
                "classification_source",
                "classification_candidates",
            ]:
                update_payload[key] = None
            update_payload["classification_path"] = []
            update_payload["classification_score"] = 0.0
            update_payload["classification_review_status"] = "needs_review"
            update_payload["classification_issue_code"] = "no_match"

        parameters = ["needs_review", "no_match"]
        update_sql = """
            UPDATE documents
            SET classification_result = NULL,
                classification_id = NULL,
                classification_path = NULL,
                classification_score = 0.0,
                classification_source = NULL,
                classification_candidates = NULL,
                classification_review_status = ?,
                classification_issue_code = ?
        """
        if has_payload:
            update_sql += ", payload = ?"
            parameters.append(json.dumps(update_payload, ensure_ascii=False))
        update_sql += " WHERE id = ?"
        parameters.append(row["id"])
        connection.execute(update_sql, tuple(parameters))
        cleared += 1

    return cleared


def backfill(db_path: str | Path | None = None) -> dict[str, int]:
    db_file = resolve_db_path(db_path)

    with connect_database(db_file) as connection:
        cleaned = _cleanup_pseudo_classifications(connection)
        ready_pending_cleared = 0
        try:
            ready_pending_cleared = _clear_ready_pending_local_content(connection)
        except Exception:
            ready_pending_cleared = 0
        status_normalized = _normalize_document_status_fields(connection)
        forced_keyword_cleared = _clear_forced_keyword_classifications(connection)
        rows = _load_pending_documents(connection)
        has_payload = _has_column(connection, "documents", "payload")
        total = len(rows)
        updated = 0
        skipped = 0

        for index, row in enumerate(rows, start=1):
            matches = search_by_keyword(str(row["classification_result"] or ""))
            best_match = matches[0] if matches else None

            if best_match and float(best_match[1]) > 0.3:
                label, score = best_match
                candidate_ids = [item[0].get("id", "") for item in matches[:5] if item[0].get("id")]
                parameters = [
                    label.get("id"),
                    json.dumps(list(label.get("path") or []), ensure_ascii=False),
                    round(float(score), 4),
                    "keyword",
                    json.dumps(candidate_ids, ensure_ascii=False),
                ]
                update_sql = """
                    UPDATE documents
                    SET classification_id = ?,
                        classification_path = ?,
                        classification_score = ?,
                        classification_source = ?,
                        classification_candidates = ?
                """
                if has_payload:
                    update_sql += ", payload = ?"
                    parameters.append(
                        _merge_payload(
                            row,
                            label=label,
                            score=score,
                            candidate_ids=candidate_ids,
                        )
                    )
                update_sql += " WHERE id = ?"
                parameters.append(row["id"])
                connection.execute(update_sql, tuple(parameters))
                updated += 1
            else:
                skipped += 1

            if index % 10 == 0 or index == total:
                print(
                    "[taxonomy-backfill] "
                    f"progress={index}/{total} "
                    f"updated={updated} "
                    f"skipped={skipped}"
                )

        connection.commit()

    summary = {
        "processed": total,
        "updated": updated,
        "skipped": skipped,
        "cleaned": cleaned,
        "ready_pending_cleared": ready_pending_cleared,
        "status_normalized": status_normalized,
        "forced_keyword_cleared": forced_keyword_cleared,
    }
    print(
        "[taxonomy-backfill] "
        f"processed={summary['processed']} "
        f"updated={summary['updated']} "
        f"skipped={summary['skipped']} "
        f"cleaned={summary['cleaned']} "
        f"ready_pending_cleared={summary['ready_pending_cleared']} "
        f"status_normalized={summary['status_normalized']} "
        f"forced_keyword_cleared={summary['forced_keyword_cleared']}"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill taxonomy ids from classification_result")
    parser.add_argument("--db-path", default=None, help="Override SQLite database path")
    args = parser.parse_args(argv)

    backfill(db_path=args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
