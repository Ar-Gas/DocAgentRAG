import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.services.document_label_resolver as resolver_module  # noqa: E402


def test_resolve_document_label_uses_preview_or_full_content(monkeypatch):
    monkeypatch.setattr(
        resolver_module,
        "get_document_content_record",
        lambda document_id: {
            "preview_content": "",
            "full_content": "本协议约定劳动期限、薪酬与保密义务。",
        },
    )

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "labor-contract.docx"
            assert text == "本协议约定劳动期限、薪酬与保密义务。"
            return "劳动合同"

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-2",
            {"id": "doc-2", "filename": "labor-contract.docx", "preview_content": ""},
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["is_error"] is False
    assert result["source"] == "llm"


def test_resolve_document_label_returns_error_for_parser_failure(monkeypatch):
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: None)

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-3",
            {
                "id": "doc-3",
                "filename": "broken.docx",
                "preview_content": "Word处理失败: Package not found at '/tmp/broken.docx'",
            },
            llm_gateway=None,
        )
    )

    assert result == {
        "label": "Error",
        "source_text": "",
        "is_error": True,
        "source": "error_text",
    }


def test_resolve_document_label_returns_error_for_html_interstitial(monkeypatch):
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: None)

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-4",
            {
                "id": "doc-4",
                "filename": "blocked.pdf",
                "preview_content": "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>",
            },
            llm_gateway=None,
        )
    )

    assert result == {
        "label": "Error",
        "source_text": "",
        "is_error": True,
        "source": "error_text",
    }


def test_resolve_document_label_normalizes_llm_label(monkeypatch):
    monkeypatch.setattr(
        resolver_module,
        "get_document_content_record",
        lambda document_id: {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
    )

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "labor-contract.docx"
            assert text == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
            return "  分类标签： 劳动合同  "

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-5",
            {"id": "doc-5", "filename": "labor-contract.docx", "preview_content": ""},
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["source_text"] == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
    assert result["is_error"] is False
    assert result["source"] == "llm"


def test_resolve_document_label_uses_excerpt_when_primary_fields_missing(monkeypatch):
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: None)

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "labor-contract.docx"
            assert text == "本协议约定劳动期限、薪酬与保密义务。"
            return "劳动合同"

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-6",
            {
                "id": "doc-6",
                "filename": "labor-contract.docx",
                "preview_content": "",
                "full_content": "",
                "content": "",
                "excerpt": "本协议约定劳动期限、薪酬与保密义务。",
                "summary_source": "备用摘要文本",
            },
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["source_text"] == "本协议约定劳动期限、薪酬与保密义务。"
    assert result["is_error"] is False
    assert result["source"] == "llm"


def test_resolve_document_label_uses_summary_source_when_excerpt_is_unusable(monkeypatch):
    monkeypatch.setattr(resolver_module, "get_document_content_record", lambda document_id: None)

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "labor-contract.docx"
            assert text == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
            return "劳动合同"

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-7",
            {
                "id": "doc-7",
                "filename": "labor-contract.docx",
                "preview_content": "",
                "full_content": "",
                "content": "",
                "excerpt": "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>",
                "summary_source": "甲方与乙方签署劳动合同，并约定试用期与薪酬。",
            },
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["source_text"] == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
    assert result["is_error"] is False
    assert result["source"] == "llm"


def test_resolve_document_label_uses_filename_heuristic_when_llm_label_invalid(monkeypatch):
    monkeypatch.setattr(
        resolver_module,
        "get_document_content_record",
        lambda document_id: {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
    )

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "劳动合同.docx"
            assert text == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
            return "文档"

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-8",
            {"id": "doc-8", "filename": "劳动合同.docx", "preview_content": ""},
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["source_text"] == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
    assert result["is_error"] is False
    assert result["source"] == "heuristic"


def test_resolve_document_label_falls_back_to_filename_heuristic_when_llm_raises(monkeypatch):
    monkeypatch.setattr(
        resolver_module,
        "get_document_content_record",
        lambda document_id: {"preview_content": "甲方与乙方签署劳动合同，并约定试用期与薪酬。"},
    )

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "劳动合同.docx"
            assert text == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
            raise RuntimeError("mock llm failure")

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-9",
            {"id": "doc-9", "filename": "劳动合同.docx", "preview_content": ""},
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "劳动合同"
    assert result["source_text"] == "甲方与乙方签署劳动合同，并约定试用期与薪酬。"
    assert result["is_error"] is False
    assert result["source"] == "heuristic"


def test_resolve_document_label_heuristic_error_label_should_be_marked_as_error(monkeypatch):
    monkeypatch.setattr(
        resolver_module,
        "get_document_content_record",
        lambda document_id: {"preview_content": "这是一段可用内容"},
    )

    class FakeGateway:
        async def classify(self, title, text, candidates=None):
            assert title == "Error.docx"
            assert text == "这是一段可用内容"
            return "文档"

    result = asyncio.run(
        resolver_module.resolve_document_label(
            "doc-10",
            {"id": "doc-10", "filename": "Error.docx", "preview_content": ""},
            llm_gateway=FakeGateway(),
        )
    )

    assert result["label"] == "Error"
    assert result["source_text"] == "这是一段可用内容"
    assert result["is_error"] is True
    assert result["source"] == "heuristic"
