"""
一次性迁移脚本：将 backend/data/*.json 导入 SQLite metadata store。

使用方法（在 backend/ 目录下执行）：
    python scripts/migrate_json_to_sqlite.py

注意：
- 迁移后原 JSON 文件不会被删除（保留为只读快照）
- 已存在于 SQLite 的文档会被跳过（不覆盖）
- 运行后可通过 --verify 参数验证迁移结果
"""
import sys
import json
import argparse
from pathlib import Path

# 确保 backend/ 目录在 Python 路径中
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import DATA_DIR
from utils.storage import _metadata_store


def migrate(dry_run: bool = False) -> tuple[int, int, int]:
    """
    返回 (migrated, skipped, errors)
    """
    store = _metadata_store()
    migrated, skipped, errors = 0, 0, 0

    json_files = sorted(DATA_DIR.glob("*.json"))
    if not json_files:
        print("未找到任何 JSON 文件，无需迁移。")
        return 0, 0, 0

    print(f"发现 {len(json_files)} 个 JSON 文件，开始迁移...\n")

    for json_path in json_files:
        try:
            doc_info = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [ERROR] 读取 {json_path.name} 失败: {exc}")
            errors += 1
            continue

        doc_id = doc_info.get("id")
        if not doc_id:
            print(f"  [SKIP]  {json_path.name} 缺少 id 字段，跳过")
            skipped += 1
            continue

        existing = store.get_document(doc_id)
        if existing is not None:
            print(f"  [SKIP]  {doc_info.get('filename', doc_id)} 已存在于 SQLite，跳过")
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY]   将迁移: {doc_info.get('filename', doc_id)}")
            migrated += 1
            continue

        try:
            store.upsert_document(doc_info, mirror=False)
            print(f"  [OK]    {doc_info.get('filename', doc_id)}")
            migrated += 1
        except Exception as exc:
            print(f"  [ERROR] 迁移 {doc_info.get('filename', doc_id)} 失败: {exc}")
            errors += 1

    return migrated, skipped, errors


def verify() -> None:
    store = _metadata_store()
    json_files = list(DATA_DIR.glob("*.json"))
    all_docs = store.get_all_documents()
    sqlite_ids = {d["id"] for d in all_docs if d.get("id")}
    json_ids = set()
    for jf in json_files:
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
            if d.get("id"):
                json_ids.add(d["id"])
        except Exception:
            pass

    missing_in_sqlite = json_ids - sqlite_ids
    print(f"\n验证结果:")
    print(f"  JSON 文件数: {len(json_ids)}")
    print(f"  SQLite 记录数: {len(sqlite_ids)}")
    if missing_in_sqlite:
        print(f"  ⚠️  以下文档在 JSON 中存在但 SQLite 缺失 ({len(missing_in_sqlite)} 个):")
        for mid in list(missing_in_sqlite)[:10]:
            print(f"    - {mid}")
    else:
        print("  ✅ 所有 JSON 文档均已存在于 SQLite")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 JSON 文档元数据迁移到 SQLite")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要迁移的内容，不实际写入")
    parser.add_argument("--verify", action="store_true", help="迁移后验证一致性")
    args = parser.parse_args()

    migrated, skipped, errors = migrate(dry_run=args.dry_run)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}迁移完成:")
    print(f"  成功: {migrated} 个")
    print(f"  跳过: {skipped} 个（已存在）")
    print(f"  失败: {errors} 个")

    if args.verify and not args.dry_run:
        verify()

    sys.exit(1 if errors else 0)
