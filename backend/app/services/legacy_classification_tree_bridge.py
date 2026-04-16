import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def update_classification_tree_after_add(doc_info: Dict) -> None:
    try:
        from utils.multi_level_classifier import build_and_save_classification_tree, get_multi_level_classifier

        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        if not tree or "tree" not in tree:
            build_and_save_classification_tree()
            return

        classification = classifier.classify_document(doc_info)
        if not classification:
            return

        content_cat = classification["content_category"]
        file_type = classification["file_type"]
        time_group = classification["time_group"]
        tree["tree"].setdefault(content_cat, {})
        tree["tree"][content_cat].setdefault(file_type, {})
        tree["tree"][content_cat][file_type].setdefault(time_group, [])
        tree["tree"][content_cat][file_type][time_group].append(classification)
        tree["total_documents"] = tree.get("total_documents", 0) + 1
        tree["updated_at"] = datetime.now().isoformat()
        classifier.save_classification_tree(tree)
        logger.info("分类树已更新（新增文档）: %s", doc_info.get("filename"))
    except Exception as exc:
        logger.error("新增文档后更新分类树失败: %s", exc)


def update_classification_tree_after_reclassify(
    document_id: str,
    old_classification: Optional[str],
    new_classification: Optional[Dict],
    *,
    get_document_info,
) -> None:
    try:
        from utils.multi_level_classifier import get_multi_level_classifier

        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        if not tree or "tree" not in tree:
            return

        doc_info = get_document_info(document_id)
        if not doc_info:
            return

        tree_modified = False
        if old_classification:
            for content_cat, types in list(tree["tree"].items()):
                for file_type, times in list(types.items()):
                    for time_group, docs in list(times.items()):
                        original_count = len(docs)
                        tree["tree"][content_cat][file_type][time_group] = [
                            doc for doc in docs if doc.get("document_id") != document_id
                        ]
                        if len(tree["tree"][content_cat][file_type][time_group]) != original_count:
                            tree_modified = True
                        if not tree["tree"][content_cat][file_type][time_group]:
                            del tree["tree"][content_cat][file_type][time_group]
                    if not tree["tree"][content_cat][file_type]:
                        del tree["tree"][content_cat][file_type]
                if not tree["tree"][content_cat]:
                    del tree["tree"][content_cat]

        if new_classification:
            content_cat = new_classification.get("content_category")
            file_type = new_classification.get("file_type")
            time_group = new_classification.get("time_group")
            if content_cat and file_type and time_group:
                tree["tree"].setdefault(content_cat, {})
                tree["tree"][content_cat].setdefault(file_type, {})
                tree["tree"][content_cat][file_type].setdefault(time_group, [])
                tree["tree"][content_cat][file_type][time_group].append(new_classification)
                tree_modified = True

        if tree_modified:
            tree["updated_at"] = datetime.now().isoformat()
            classifier.save_classification_tree(tree)
            logger.info("分类树已更新（重新分类）: %s", document_id)
    except Exception as exc:
        logger.error("重新分类后更新分类树失败: %s", exc)


def update_classification_tree_after_delete(document_id: str) -> None:
    try:
        from utils.multi_level_classifier import get_multi_level_classifier

        classifier = get_multi_level_classifier()
        tree = classifier.load_classification_tree()
        if not tree or "tree" not in tree:
            return

        tree_modified = False
        for content_cat, types in list(tree["tree"].items()):
            for file_type, times in list(types.items()):
                for time_group, docs in list(times.items()):
                    original_count = len(docs)
                    tree["tree"][content_cat][file_type][time_group] = [
                        doc for doc in docs if doc.get("document_id") != document_id
                    ]
                    if len(tree["tree"][content_cat][file_type][time_group]) != original_count:
                        tree_modified = True
                    if not tree["tree"][content_cat][file_type][time_group]:
                        del tree["tree"][content_cat][file_type][time_group]
                if not tree["tree"][content_cat][file_type]:
                    del tree["tree"][content_cat][file_type]
            if not tree["tree"][content_cat]:
                del tree["tree"][content_cat]

        if tree_modified:
            tree["total_documents"] = max(0, tree.get("total_documents", 0) - 1)
            tree["updated_at"] = datetime.now().isoformat()
            classifier.save_classification_tree(tree)
            logger.info("分类树已更新（删除文档）: %s", document_id)
    except Exception as exc:
        logger.error("删除文档后更新分类树失败: %s", exc)
