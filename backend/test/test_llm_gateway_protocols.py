import os
import sys
import asyncio
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from app.domain.llm.config import LLMConfig  # noqa: E402
from app.domain.llm.gateway import LLMGateway, LLMResponse  # noqa: E402


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


def test_call_doubao_falls_back_to_chat_completions_when_responses_has_only_reasoning(monkeypatch):
    gateway = _build_gateway("https://ark.cn-beijing.volces.com/api/v3/responses")

    responses_reply = Mock()
    responses_reply.status_code = 200
    responses_reply.json.return_value = {
        "output": [
            {
                "type": "reasoning",
                "status": "incomplete",
                "summary": [
                    {"type": "summary_text", "text": "思考中"},
                ],
            }
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 128,
            "total_tokens": 138,
        },
    }

    chat_reply = Mock()
    chat_reply.status_code = 200
    chat_reply.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "金融是资金融通与风险配置活动的总称。"
                }
            }
        ],
        "usage": {"total_tokens": 256},
    }

    post = Mock(side_effect=[responses_reply, chat_reply])
    monkeypatch.setattr(requests, "post", post)

    result = gateway._call_doubao("什么是金融", "doubao-test", max_tokens=512, temperature=0.1)

    assert result.content == "金融是资金融通与风险配置活动的总称。"
    assert result.tokens_used == 256
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"] == {
        "model": "doubao-test",
        "input": "什么是金融",
        "max_output_tokens": 512,
        "temperature": 0.1,
    }
    assert post.call_args_list[1].args[0] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    assert post.call_args_list[1].kwargs["json"] == {
        "model": "doubao-test",
        "messages": [{"role": "user", "content": "什么是金融"}],
        "max_tokens": 512,
        "temperature": 0.1,
    }


def test_call_qa_prefers_chat_completions_when_api_url_is_responses(monkeypatch):
    gateway = _build_gateway("https://ark.cn-beijing.volces.com/api/v3/responses")

    chat_reply = Mock()
    chat_reply.status_code = 200
    chat_reply.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "金融是资金融通与风险配置活动的总称。"
                }
            }
        ],
        "usage": {"total_tokens": 256},
    }

    post = Mock(return_value=chat_reply)
    monkeypatch.setattr(requests, "post", post)

    result = asyncio.run(
        gateway.call("什么是金融", task="qa", max_tokens=512, temperature=0.1, use_cache=False)
    )

    assert result.content == "金融是资金融通与风险配置活动的总称。"
    assert result.tokens_used == 256
    assert post.call_count == 1
    assert post.call_args.args[0] == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    assert post.call_args.kwargs["json"] == {
        "model": gateway.config.get_model("qa"),
        "messages": [{"role": "user", "content": "什么是金融"}],
        "max_tokens": 512,
        "temperature": 0.1,
    }


def test_call_passes_task_timeout_to_provider(monkeypatch):
    gateway = _build_gateway("https://ark.cn-beijing.volces.com/api/v3/responses")
    gateway.config.timeout_for_task["qa"] = 77
    captured = {}

    def fake_call_doubao(*args, **kwargs):
        captured["kwargs"] = kwargs
        return LLMResponse(content="ok", tokens_used=1, model="fake")

    monkeypatch.setattr(gateway, "_call_doubao", fake_call_doubao)

    result = asyncio.run(
        gateway.call("什么是金融", task="qa", max_tokens=512, temperature=0.1, use_cache=False)
    )

    assert result.content == "ok"
    assert captured["kwargs"]["request_timeout_seconds"] == 77
