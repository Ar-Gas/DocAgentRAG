import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.taxonomy_classifier import TaxonomyClassifier  # noqa: E402


class _UnusedGateway:
    async def call(self, prompt, task="classify", max_tokens=50, temperature=0.0, use_cache=False):
        raise AssertionError("LLM should not be called in this case")


class _GatewayReturningRelease:
    async def call(self, prompt, task="classify", max_tokens=50, temperature=0.0, use_cache=False):
        assert "候选标签" in prompt
        assert "发布说明" in prompt
        return type("Response", (), {"content": "发布说明"})()


class _GatewayReturningAdminNotice:
    async def call(self, prompt, task="classify", max_tokens=50, temperature=0.0, use_cache=False):
        assert "候选标签" in prompt
        assert "通知公告" in prompt
        return type("Response", (), {"content": "通知公告"})()


class _GatewayFailure:
    async def call(self, prompt, task="classify", max_tokens=50, temperature=0.0, use_cache=False):
        raise RuntimeError("gateway unavailable")


def test_recall_candidates_adds_file_type_bonus():
    classifier = TaxonomyClassifier(llm_gateway=_UnusedGateway())

    without_bonus = classifier._recall_candidates(
        "版本更新内容与发布节奏说明",
        filename="版本更新说明.txt",
        file_type=".txt",
        top_k=3,
    )
    with_bonus = classifier._recall_candidates(
        "版本更新内容与发布节奏说明",
        filename="版本说明.md",
        file_type=".md",
        top_k=3,
    )

    assert without_bonus[0][0]["id"] == "product.release"
    assert with_bonus[0][0]["id"] == "product.release"
    assert round(with_bonus[0][1] - without_bonus[0][1], 4) == 0.3


def test_classify_returns_keyword_when_top_candidate_is_clear():
    classifier = TaxonomyClassifier(llm_gateway=_UnusedGateway())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-1",
            content="候选人录用审批，需要确认薪资包、职级、offer和入职日期。",
            filename="offer审批表.docx",
            file_type=".docx",
        )
    )

    assert result["classification_id"] == "hr.offer_approval"
    assert result["classification_label"] == "Offer审批"
    assert result["classification_source"] == "keyword"
    assert result["classification_score"] >= 0.8
    assert result["classification_candidates"][0] == "hr.offer_approval"


def test_classify_returns_llm_selected_candidate():
    classifier = TaxonomyClassifier(llm_gateway=_GatewayReturningRelease())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-2",
            content="本次版本更新涉及功能优化和发布节奏调整。",
            filename="release_note_v3.md",
            file_type=".md",
        )
    )

    assert result["classification_id"] == "product.release"
    assert result["classification_label"] == "发布说明"
    assert result["classification_source"] == "llm"
    assert result["classification_score"] >= 0.7


def test_classify_uses_template_llm_selection_when_candidates_are_weak():
    classifier = TaxonomyClassifier(llm_gateway=_GatewayReturningAdminNotice())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-3",
            content="hello world random text",
            filename="misc.txt",
            file_type=".txt",
        )
    )

    assert result["classification_id"] == "admin.notice"
    assert result["classification_label"] == "通知公告"
    assert result["classification_source"] == "llm_forced"
    assert 0.0 < result["classification_score"] < 0.5
    assert "admin.unclassified" not in result["classification_candidates"]


def test_classify_uses_best_template_candidate_when_llm_fails():
    classifier = TaxonomyClassifier(llm_gateway=_GatewayFailure())

    result = asyncio.run(
        classifier.classify(
            document_id="doc-4",
            content="本次版本更新涉及功能优化和发布节奏调整。",
            filename="release_note_v3.md",
            file_type=".md",
        )
    )

    assert result["classification_id"] == "product.release"
    assert result["classification_label"] == "发布说明"
    assert result["classification_source"] == "keyword_forced"
    assert result["classification_score"] > 0
    assert "admin.unclassified" not in result["classification_candidates"]
