import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from app.domain.llm.config import LLMConfig  # noqa: E402
from app.domain.llm.gateway import LLMGateway  # noqa: E402


def _build_gateway(api_url: str) -> LLMGateway:
    config = LLMConfig()
    config.api_key = "test-key"
    config.api_url = api_url
    config.semantic_cache_enabled = False
    return LLMGateway(config=config)


def test_call_doubao_uses_chat_completions_payload_and_parses_choices(monkeypatch):
    gateway = _build_gateway("https://ark.cn-beijing.volces.com/api/v3/chat/completions")

    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "chat answer"}}],
        "usage": {"total_tokens": 42},
    }

    post = Mock(return_value=fake_response)
    monkeypatch.setattr(requests, "post", post)

    result = gateway._call_doubao("hello", "doubao-test", max_tokens=123, temperature=0.2)

    assert result.content == "chat answer"
    assert result.tokens_used == 42
    assert post.call_args.kwargs["json"] == {
        "model": "doubao-test",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 123,
        "temperature": 0.2,
    }


def test_call_doubao_uses_responses_payload_and_parses_output_text(monkeypatch):
    gateway = _build_gateway("https://ark.cn-beijing.volces.com/api/v3/responses")

    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "output_text": "responses answer",
        "usage": {"total_tokens": 18},
    }

    post = Mock(return_value=fake_response)
    monkeypatch.setattr(requests, "post", post)

    result = gateway._call_doubao("hello", "doubao-test", max_tokens=77, temperature=0.0)

    assert result.content == "responses answer"
    assert result.tokens_used == 18
    assert post.call_args.kwargs["json"] == {
        "model": "doubao-test",
        "input": "hello",
        "max_output_tokens": 77,
        "temperature": 0.0,
    }


def test_call_doubao_parses_responses_output_array_when_output_text_missing(monkeypatch):
    gateway = _build_gateway("https://ark.cn-beijing.volces.com/api/v3/responses")

    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "structured "},
                    {"type": "output_text", "text": "answer"},
                ]
            }
        ],
        "usage": {"total_tokens": 9},
    }

    monkeypatch.setattr(requests, "post", Mock(return_value=fake_response))

    result = gateway._call_doubao("hello", "doubao-test")

    assert result.content == "structured answer"
    assert result.tokens_used == 9
