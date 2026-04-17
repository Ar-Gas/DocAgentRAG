import shutil
from pathlib import Path
from typing import Callable, List, Optional, Union

from app.core.logger import logger


def ordered_document_search_roots(base_dir: Path, doc_dir: Path, original_path: str) -> List[Path]:
    normalized = (original_path or "").replace("\\", "/")
    classified_dir = base_dir / "classified_docs"
    test_data_dir = base_dir / "test" / "test_date"
    repo_root = base_dir.parent

    if "/test/test_date/" in normalized:
        roots = [test_data_dir, classified_dir, doc_dir, repo_root]
    elif "/classified_docs/" in normalized:
        roots = [classified_dir, doc_dir, test_data_dir, repo_root]
    else:
        roots = [classified_dir, doc_dir, test_data_dir, repo_root]

    deduped: List[Path] = []
    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        deduped.append(root)
    return deduped


def candidate_document_names(doc_info: dict) -> List[str]:
    names: List[str] = []
    filepath = (doc_info.get("filepath") or "").strip()
    filename = (doc_info.get("filename") or "").strip()

    basename = Path(filepath).name if filepath else ""
    for item in [basename, filename]:
        if item and item not in names:
            names.append(item)
    return names


def path_exists_safely(path_value: str) -> bool:
    if not path_value:
        return False
    try:
        return Path(path_value).exists()
    except OSError:
        return False


def resolve_document_filepath(
    document_or_id: Union[str, dict],
    *,
    base_dir: Path,
    doc_dir: Path,
    get_document_info: Callable[[str], Optional[dict]],
    update_document_info: Callable[[str, dict], bool],
    persist: bool = True,
) -> Optional[str]:
    doc_info = get_document_info(document_or_id) if isinstance(document_or_id, str) else document_or_id
    if not doc_info:
        return None

    current_path = (doc_info.get("filepath") or "").strip()
    if path_exists_safely(current_path):
        resolved = str(Path(current_path).resolve())
        if persist and doc_info.get("id") and resolved != current_path:
            update_document_info(doc_info["id"], {"filepath": resolved})
        return resolved

    names = candidate_document_names(doc_info)
    if not names:
        return None

    for root in ordered_document_search_roots(base_dir, doc_dir, current_path):
        if not root.exists():
            continue
        for name in names:
            for candidate in root.rglob(name):
                if not candidate.is_file():
                    continue
                resolved = str(candidate.resolve())
                if persist and doc_info.get("id") and resolved != current_path:
                    update_document_info(doc_info["id"], {"filepath": resolved})
                return resolved
    return None


def enrich_document_file_state(
    doc_info: Optional[dict],
    *,
    base_dir: Path,
    doc_dir: Path,
    get_document_info: Callable[[str], Optional[dict]],
    update_document_info: Callable[[str, dict], bool],
    persist: bool = True,
) -> dict:
    enriched = dict(doc_info or {})
    resolved_path = resolve_document_filepath(
        enriched,
        base_dir=base_dir,
        doc_dir=doc_dir,
        get_document_info=get_document_info,
        update_document_info=update_document_info,
        persist=persist,
    )
    enriched["filepath"] = resolved_path or enriched.get("filepath", "")
    enriched["file_available"] = bool(resolved_path)
    return enriched


def create_classification_directory(
    doc_info: dict,
    categories: List[str],
    base_dir: Optional[Path] = None,
) -> tuple[bool, str]:
    try:
        if not categories or not doc_info.get("filepath"):
            return False, ""

        target_root = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2] / "classified_docs"
        target_root.mkdir(parents=True, exist_ok=True)

        category_dir = target_root / categories[0]
        category_dir.mkdir(parents=True, exist_ok=True)

        original_path = Path(doc_info["filepath"])
        if not original_path.exists():
            logger.warning("原文件不存在，跳过移动：{}", original_path)
            return False, ""

        target_path = category_dir / original_path.name
        counter = 1
        while target_path.exists():
            target_path = category_dir / f"{original_path.stem}_{counter}{original_path.suffix}"
            counter += 1

        shutil.move(str(original_path), str(target_path))
        logger.info("文件已移动到分类目录：{} -> {}", original_path.name, target_path)
        return True, str(target_path)
    except Exception as exc:
        logger.opt(exception=exc).error("创建分类目录/移动文件失败")
        return False, ""
