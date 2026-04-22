import os
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.taxonomy import universal_taxonomy_v3  # noqa: E402
from app.domain.taxonomy.universal_taxonomy_v3 import (  # noqa: E402
    TAXONOMY_VERSION,
    get_all_labels,
    get_domain_fallback,
    get_domain_options,
    get_label_by_id,
    get_label_by_path,
    get_labels_by_domain,
    infer_domain_from_filename,
)


def test_taxonomy_v3_catalog_shape_and_size():
    labels = get_all_labels()
    paths = [tuple(label["path"]) for label in labels]
    ids = [label["id"] for label in labels]

    assert TAXONOMY_VERSION == "taxonomy_v3"
    assert len(labels) == 346
    assert len(paths) == len(set(paths))
    assert len(ids) == len(set(ids))
    assert all(len(label["path"]) == 3 for label in labels)


def test_taxonomy_v3_domains_have_single_fallback_leaf():
    domains = get_domain_options()

    assert "办公文档" in domains
    assert "图书资料" in domains
    assert "研究分析" in domains

    for domain in domains:
        fallback = get_domain_fallback(domain)
        domain_labels = get_labels_by_domain(domain)
        fallback_labels = [label for label in domain_labels if label.get("fallback")]

        assert fallback["path"][0] == domain
        assert len(fallback["path"]) == 3
        assert len(fallback_labels) == 1
        assert fallback_labels[0]["id"] == fallback["id"]


def test_taxonomy_v3_unknown_domain_has_no_fallback():
    assert get_domain_fallback("不存在的一级域") is None
    assert get_domain_fallback("") is None


def test_taxonomy_v3_can_lookup_book_and_office_paths():
    assert get_label_by_path(["图书资料", "计算机图书", "编程语言书籍"])["id"] == "books.computer.programming_language"
    assert get_label_by_path(["办公文档", "综合办公", "通用办公材料"])["fallback"] is True
    assert get_label_by_path(["研发技术", "综合技术", "通用技术文档"])["fallback"] is True


def test_taxonomy_v3_filename_domain_heuristics_prefer_books_for_book_titles():
    assert infer_domain_from_filename("Rust编程：入门、实战与进阶.pdf", ".pdf") == "图书资料"
    assert infer_domain_from_filename("操作系统导论.pdf", ".pdf") == "图书资料"
    assert infer_domain_from_filename("付款审批单.xlsx", ".xlsx") == "财务税务"


def test_taxonomy_v3_catalog_helpers_return_safe_copies():
    original = get_label_by_path(["图书资料", "计算机图书", "编程语言书籍"])

    original["path"][0] = "污染"
    original["keywords"].append("污染")

    fresh_by_path = get_label_by_path(["图书资料", "计算机图书", "编程语言书籍"])
    fresh_by_id = get_label_by_id("books.computer.programming_language")
    all_labels = get_all_labels()
    all_labels[0]["path"][0] = "污染"

    assert fresh_by_path["path"] == ["图书资料", "计算机图书", "编程语言书籍"]
    assert "污染" not in fresh_by_path["keywords"]
    assert fresh_by_id["path"] == ["图书资料", "计算机图书", "编程语言书籍"]
    assert get_all_labels()[0]["path"][0] != "污染"


def test_taxonomy_v3_catalog_rejects_generated_id_collisions(monkeypatch):
    monkeypatch.setattr(universal_taxonomy_v3, "_label_id", lambda *_args: "duplicate.id")

    try:
        universal_taxonomy_v3._build_catalog()
    except ValueError as exc:
        assert "Duplicate taxonomy_v3 label id" in str(exc)
    else:
        raise AssertionError("Expected duplicate label ids to fail fast")


def test_taxonomy_v3_ids_are_stable_across_hash_seeds():
    script = (
        "import sys; "
        "sys.path.append('backend'); "
        "from app.domain.taxonomy.universal_taxonomy_v3 import get_label_by_path; "
        "print(get_label_by_path(['办公文档', '会议纪要', '会议纪要'])['id'])"
    )

    env_1 = {**os.environ, "PYTHONHASHSEED": "1"}
    env_2 = {**os.environ, "PYTHONHASHSEED": "2"}

    first = subprocess.check_output([sys.executable, "-c", script], text=True, env=env_1).strip()
    second = subprocess.check_output([sys.executable, "-c", script], text=True, env=env_2).strip()

    assert first == second
