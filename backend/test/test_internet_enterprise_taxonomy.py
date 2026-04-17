import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.taxonomy.internet_enterprise_taxonomy import (  # noqa: E402
    TAXONOMY,
    get_all_labels,
    get_label_by_id,
    search_by_keyword,
)


def test_taxonomy_has_16_domains():
    assert len(TAXONOMY) == 16


def test_get_label_by_id_returns_expected_leaf():
    label = get_label_by_id("hr.offer_approval")

    assert label is not None
    assert label["label"] == "Offer审批"
    assert label["path"] == ["人力资源", "招聘管理", "Offer审批"]


def test_get_all_labels_returns_flat_labels():
    labels = get_all_labels()
    ids = {item["id"] for item in labels}

    assert "finance.expense" in ids
    assert "legal.contract" in ids
    assert "engineering.architecture" in ids


def test_search_by_keyword_ranks_offer_approval_highest():
    results = search_by_keyword("候选人薪资包审批，确认职级和offer入职日期")

    assert results
    assert results[0][0]["id"] == "hr.offer_approval"
    assert results[0][1] > 0


def test_search_by_keyword_supports_filename_bonus():
    results = search_by_keyword(
        "版本更新内容与发布节奏说明",
        filename_text="release_note_v3_版本说明.md",
    )

    assert results
    assert results[0][0]["id"] == "product.release"
