"""
批量回填文档 block 索引状态脚本。

使用方法（在 backend/ 目录下执行）：
    python3 scripts/backfill_block_index.py
    python3 scripts/backfill_block_index.py --failed-only
    python3 scripts/backfill_block_index.py --document-id <doc-id>
"""
import argparse
import os
import sys
import zipfile
from pathlib import Path

# 确保 backend/ 目录在 Python 路径中
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.infra.repositories.document_repository import DocumentRepository
from app.services.indexing_service import IndexingService
from config import DATA_DIR


def _document_repository() -> DocumentRepository:
    return DocumentRepository(data_dir=DATA_DIR)


def get_all_documents():
    return _document_repository().list_all()


def get_document_info(document_id: str):
    return _document_repository().get(document_id)

SUPPORTED_BLOCK_FILE_TYPES = {".pdf", ".docx", ".doc"}


def _normalize_file_type(doc_info: dict) -> str:
    file_type = (doc_info.get("file_type") or "").strip().lower()
    if file_type:
        return file_type if file_type.startswith(".") else f".{file_type}"
    filepath = (doc_info.get("filepath") or "").strip()
    return Path(filepath).suffix.lower()


def _get_skip_reason(doc_info: dict) -> str:
    file_type = _normalize_file_type(doc_info)
    if file_type not in SUPPORTED_BLOCK_FILE_TYPES:
        return f"unsupported file type: {file_type or '(none)'}"

    filepath = (doc_info.get("filepath") or "").strip()
    if not filepath:
        return "missing source filepath"

    source_path = Path(filepath)
    try:
        exists = source_path.exists()
    except OSError:
        return f"source file not readable: {filepath}"

    if not exists:
        return f"source file missing: {filepath}"
    if not os.access(source_path, os.R_OK):
        return f"source file not readable: {filepath}"
    if file_type == ".docx" and not zipfile.is_zipfile(source_path):
        return f"invalid docx package: {filepath}"

    return ""


def _select_candidates(document_id: str = "", failed_only: bool = False, limit: int = 0) -> list[str]:
    if document_id:
        doc_info = get_document_info(document_id)
        return [document_id] if doc_info else []

    candidates: list[str] = []
    for doc in get_all_documents():
        doc_id = doc.get("id")
        if not doc_id:
            continue
        status = (doc.get("block_index_status") or "").strip().lower()
        if failed_only:
            if status != "failed":
                continue
        else:
            if status == "ready":
                continue
        candidates.append(doc_id)

    if limit > 0:
        candidates = candidates[:limit]
    return candidates


def backfill(document_id: str = "", failed_only: bool = False, limit: int = 0, dry_run: bool = False) -> int:
    candidate_ids = _select_candidates(document_id=document_id, failed_only=failed_only, limit=limit)
    if not candidate_ids:
        if document_id:
            print(f"未找到文档: {document_id}")
        else:
            print("未找到需要回填的文档。")
        return 0

    service = IndexingService()
    success_count = 0
    failed_count = 0
    skipped_count = 0
    actionable_ids: list[tuple[str, dict]] = []
    skipped_docs: list[tuple[str, str]] = []

    for doc_id in candidate_ids:
        doc_info = get_document_info(doc_id) or {}
        skip_reason = _get_skip_reason(doc_info)
        if skip_reason:
            skipped_docs.append((doc_id, skip_reason))
            continue
        actionable_ids.append((doc_id, doc_info))

    print(f"待处理文档数: {len(actionable_ids)}")

    for doc_id, skip_reason in skipped_docs:
        print(f"[SKIP] {doc_id} - {skip_reason}")
        skipped_count += 1

    for doc_id, _doc_info in actionable_ids:
        if dry_run:
            print(f"[DRY] {doc_id}")
            skipped_count += 1
            continue

        result = service.index_document(doc_id, force=True)
        status = (result or {}).get("block_index_status")
        if status == "ready":
            print(f"[OK]  {doc_id}")
            success_count += 1
            continue

        error = (result or {}).get("error", "unknown error")
        print(f"[FAIL] {doc_id} - {error}")
        failed_count += 1

    print("\n回填完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {failed_count}")
    print(f"  跳过: {skipped_count}")

    return 1 if failed_count else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填文档 block 索引")
    parser.add_argument("--document-id", default="", help="仅处理指定文档ID")
    parser.add_argument("--failed-only", action="store_true", help="仅重试 block_index_status=failed 的文档")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个文档，0 表示不限制")
    parser.add_argument("--dry-run", action="store_true", help="仅打印待处理文档，不实际执行")
    args = parser.parse_args()

    exit_code = backfill(
        document_id=args.document_id,
        failed_only=args.failed_only,
        limit=max(args.limit, 0),
        dry_run=args.dry_run,
    )
    sys.exit(exit_code)
