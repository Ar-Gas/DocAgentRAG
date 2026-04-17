import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.infra.embedding_provider as embedding_provider_module  # noqa: E402
import app.services.topic_labeler as topic_labeler_module  # noqa: E402
from app.services.topic_labeler import TopicLabeler  # noqa: E402


def _representatives():
    return [
        {
            "filename": "audit-plan.pdf",
            "excerpt": "年度审计计划与整改安排",
            "summary_source": "年度审计计划、审计范围、执行安排",
        },
        {
            "filename": "audit-report.pdf",
            "excerpt": "年度审计报告与整改跟踪",
            "summary_source": "年度审计报告、问题闭环、整改跟踪",
        },
    ]


def test_topic_labeler_falls_back_to_local_label_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(topic_labeler_module, "is_llm_available", lambda: False)

    payload = TopicLabeler().label_parent_topic(_representatives())

    assert payload["label"]
    assert len(payload["label"]) <= 8
    assert payload["label"] not in topic_labeler_module._GENERIC_LABELS
    assert payload["summary"]


def test_topic_labeler_falls_back_when_llm_returns_empty(monkeypatch):
    monkeypatch.setattr(topic_labeler_module, "is_llm_available", lambda: True)
    monkeypatch.setattr(topic_labeler_module, "_call_llm", lambda *args, **kwargs: None)

    payload = TopicLabeler().label_child_topic("财务治理", _representatives())

    assert payload["label"]
    assert len(payload["label"]) <= 8
    assert payload["label"] != "财务治理"
    assert payload["label"] not in topic_labeler_module._GENERIC_LABELS
    assert payload["summary"]


def test_topic_labeler_returns_error_for_processing_failures(monkeypatch):
    monkeypatch.setattr(topic_labeler_module, "is_llm_available", lambda: False)

    representatives = [
        {
            "filename": "sample.docx",
            "excerpt": "Word处理失败: Package not found at '/tmp/sample.docx'",
            "summary_source": "Word处理失败: Package not found at '/tmp/sample.docx'",
        },
        {
            "filename": "sample.xlsx",
            "excerpt": "Excel处理失败: Excel file format cannot be determined",
            "summary_source": "Excel处理失败: Excel file format cannot be determined",
        },
    ]

    payload = TopicLabeler().label_parent_topic(representatives)

    assert payload["label"] == "Error"
    assert payload["summary"]


def test_topic_labeler_returns_error_for_placeholder_and_html_noise(monkeypatch):
    monkeypatch.setattr(topic_labeler_module, "is_llm_available", lambda: False)

    representatives = [
        {
            "filename": "sample.pdf",
            "excerpt": "PDF文档内容（使用MinerU提取）",
            "summary_source": "PDF文档内容（使用MinerU提取）",
        },
        {
            "filename": "sample.pptx",
            "excerpt": "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>",
            "summary_source": "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>",
        },
    ]

    payload = TopicLabeler().label_parent_topic(representatives)

    assert payload["label"] == "Error"
    assert payload["summary"]


def test_doubao_multimodal_embed_uses_short_timeout(monkeypatch):
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    monkeypatch.setattr(embedding_provider_module, "DOUBAO_API_KEY", "doubao-key")
    monkeypatch.setattr(embedding_provider_module, "DOUBAO_EMBEDDING_API_URL", "https://doubao.test/embed")
    monkeypatch.setattr(embedding_provider_module, "DOUBAO_EMBEDDING_MODEL", "doubao-embedding-test")

    post_mock = Mock(return_value=fake_response)
    monkeypatch.setattr(embedding_provider_module.requests, "post", post_mock)

    payload = embedding_provider_module.doubao_multimodal_embed("年度审计")

    assert payload == [0.1, 0.2, 0.3]
    assert post_mock.call_args.kwargs["timeout"] <= 5
