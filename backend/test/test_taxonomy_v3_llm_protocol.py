import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.taxonomy_v3_llm_protocol import (  # noqa: E402
    parse_classification_output,
)


def test_parse_line_protocol_with_valid_taxonomy_path():
    parsed = parse_classification_output(
        """
        一级域: 图书资料
        二级类: 计算机图书
        三级类: 编程语言书籍
        是否兜底: 否
        置信度: 0.91
        依据: 文件名包含 Rust 编程，正文包含示例代码。
        """
    )

    assert parsed.path == ["图书资料", "计算机图书", "编程语言书籍"]
    assert parsed.label_id == "books.computer.programming_language"
    assert parsed.is_fallback is False
    assert parsed.confidence == 0.91
    assert "Rust" in parsed.reason


def test_parse_slash_separated_path():
    parsed = parse_classification_output("类别：图书资料/计算机图书/软件工程书籍")

    assert parsed.path == ["图书资料", "计算机图书", "软件工程书籍"]
    assert parsed.label_id
    assert parsed.is_fallback is False
    assert parsed.confidence == 0.0
    assert parsed.reason == ""


def test_parse_line_protocol_supports_fallback_and_clamps_confidence():
    parsed = parse_classification_output(
        """
        一级域：办公文档
        二级类：综合办公
        三级类：通用办公材料
        是否兜底：是
        置信度：1.27
        依据：无法判断更具体类别，回退到办公文档兜底类。
        """
    )

    assert parsed.path == ["办公文档", "综合办公", "通用办公材料"]
    assert parsed.is_fallback is True
    assert parsed.confidence == 1.0


def test_parse_rejects_unknown_or_incomplete_path():
    assert parse_classification_output("一级域: 图书资料\n二级类: 不存在\n三级类: 分类") is None
    assert parse_classification_output("一级域: 图书资料") is None
    assert parse_classification_output("类别：图书资料/计算机图书") is None
    assert parse_classification_output("") is None
