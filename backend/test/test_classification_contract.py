import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.classification_contract import normalize_classification_label  # noqa: E402


def test_normalize_classification_label_keeps_formal_taxonomy_labels():
    assert normalize_classification_label("技术文档") == "技术文档"
    assert normalize_classification_label("办公文档") == "办公文档"
    assert normalize_classification_label("需求文档") == "需求文档"
    assert normalize_classification_label("通用办公材料") == "通用办公材料"
    assert normalize_classification_label("通用技术文档") == "通用技术文档"
    assert normalize_classification_label("综合研究材料") == "综合研究材料"
    assert normalize_classification_label("综合书籍") == "综合书籍"


def test_normalize_classification_label_still_rejects_generic_noise():
    assert normalize_classification_label("文档") is None
    assert normalize_classification_label("资料") is None
    assert normalize_classification_label("相关内容") is None
    assert normalize_classification_label("文档内容") is None
    assert normalize_classification_label("综合文档") is None
    assert normalize_classification_label("通用文档") is None
