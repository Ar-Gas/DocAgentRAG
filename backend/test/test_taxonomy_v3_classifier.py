import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.taxonomy_v3_classifier import TaxonomyV3Classifier  # noqa: E402


class FakeGateway:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    async def call(self, prompt, task="classify", max_tokens=120, temperature=0.0, use_cache=False):
        self.prompts.append(prompt)
        content = self.outputs.pop(0)
        return type("Response", (), {"content": content})()


def test_taxonomy_v3_two_stage_classifies_programming_book():
    gateway = FakeGateway(
        [
            "一级域: 图书资料\n二级类: 综合图书\n三级类: 综合书籍\n是否兜底: 是\n置信度: 0.8\n依据: Rust 编程书籍",
            "一级域: 图书资料\n二级类: 计算机图书\n三级类: 编程语言书籍\n是否兜底: 否\n置信度: 0.93\n依据: Rust 编程和示例代码",
        ]
    )

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=gateway).classify(
            "doc-rust",
            "本书介绍 Rust 所有权、借用、生命周期和示例代码。",
            filename="Rust编程：入门、实战与进阶.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "计算机图书", "编程语言书籍"]
    assert result["classification_source"] == "llm_hierarchical"
    assert result["classification_issue_code"] is None
    assert result["taxonomy_version"] == "taxonomy_v3"
    assert len(gateway.prompts) == 2
    assert "候选一级域" in gateway.prompts[0]
    assert "图书资料/计算机图书/编程语言书籍" in gateway.prompts[1]


def test_taxonomy_v3_invalid_leaf_falls_back_inside_selected_domain():
    gateway = FakeGateway(
        [
            "一级域: 图书资料\n二级类: 综合图书\n三级类: 综合书籍\n是否兜底: 是\n置信度: 0.7\n依据: 文件名像图书",
            "一级域: 图书资料\n二级类: 不存在\n三级类: 不存在\n是否兜底: 否\n置信度: 0.7\n依据: 错误输出",
            "bad output",
        ]
    )

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=gateway).classify(
            "doc-book",
            "",
            filename="未知技术资料.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "综合图书", "综合书籍"]
    assert result["classification_source"] == "llm_hierarchical_fallback"
    assert result["classification_issue_code"] is None


def test_taxonomy_v3_llm_transport_failure_uses_specific_filename_fallback():
    class FailingGateway:
        async def call(self, *args, **kwargs):
            raise RuntimeError("network down")

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=FailingGateway()).classify(
            "doc-os",
            "",
            filename="操作系统导论.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "计算机图书", "计算机基础教材"]
    assert result["classification_source"] == "llm_hierarchical_fallback"
    assert result["classification_confidence"] >= 0.7
    assert result["classification_issue_code"] is None


def test_taxonomy_v3_uses_specific_keyword_leaf_when_llm_falls_back():
    class FailingGateway:
        async def call(self, *args, **kwargs):
            raise RuntimeError("network down")

    cases = [
        (
            "Rust编程：入门、实战与进阶.pdf",
            "Rust 所有权 借用 生命周期 编程 示例代码",
            ["图书资料", "计算机图书", "编程语言书籍"],
        ),
        (
            "操作系统导论.pdf",
            "操作系统 进程 线程 内存 文件系统 教材",
            ["图书资料", "计算机图书", "计算机基础教材"],
        ),
        (
            "重构：改善既有代码的设计.pdf",
            "重构 代码坏味道 设计模式 软件工程",
            ["图书资料", "计算机图书", "软件工程书籍"],
        ),
        (
            "浪潮之巅完整版.pdf",
            "互联网 科技公司 产业 发展史",
            ["图书资料", "科技产业图书", "互联网产业书籍"],
        ),
        (
            "中国是部金融史.pdf",
            "金融史 货币 银行 经济史",
            ["图书资料", "经济金融图书", "金融历史书籍"],
        ),
        (
            "《当代中国社会分层》李强.pdf",
            "社会分层 阶层 社会学",
            ["图书资料", "社科图书", "社会学书籍"],
        ),
    ]

    for filename, content, expected_path in cases:
        result = asyncio.run(
            TaxonomyV3Classifier(llm_gateway=FailingGateway()).classify(
                "doc-book",
                content,
                filename=filename,
                file_type=".pdf",
            )
        )

        assert result["classification_path"] == expected_path
        assert result["classification_issue_code"] is None
        assert result["taxonomy_version"] == "taxonomy_v3"


def test_taxonomy_v3_strong_filename_keyword_overrides_generic_llm_leaf():
    gateway = FakeGateway(
        [
            "一级域: 图书资料\n二级类: 综合图书\n三级类: 综合书籍\n是否兜底: 是\n置信度: 0.8\n依据: 技术书籍",
            "一级域: 图书资料\n二级类: 计算机图书\n三级类: 编程语言书籍\n是否兜底: 否\n置信度: 0.9\n依据: 代码相关",
        ]
    )

    result = asyncio.run(
        TaxonomyV3Classifier(llm_gateway=gateway).classify(
            "doc-refactor",
            "代码坏味道、重构手法、软件工程实践",
            filename="重构：改善既有代码的设计.pdf",
            file_type=".pdf",
        )
    )

    assert result["classification_path"] == ["图书资料", "计算机图书", "软件工程书籍"]
    assert result["classification_source"] == "llm_hierarchical_fallback"
    assert result["classification_issue_code"] is None
