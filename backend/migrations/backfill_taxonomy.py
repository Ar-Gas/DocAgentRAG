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


def backfill(db_path: str | Path | None = None) -> dict[str, int]:
    db_file = resolve_db_path(db_path)

    with connect_database(db_file) as connection:
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
    }
    print(
        "[taxonomy-backfill] "
        f"processed={summary['processed']} "
        f"updated={summary['updated']} "
        f"skipped={summary['skipped']}"
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
