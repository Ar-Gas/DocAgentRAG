import base64
import os
import sys
from unittest.mock import Mock

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.local_embedding_openai_service import (  # noqa: E402
    _normalize_embedding_input,
    _to_base64_embedding,
    create_embeddings_payload,
)


def test_normalize_embedding_input_accepts_string():
    assert _normalize_embedding_input("预算审批流程") == ["预算审批流程"]


def test_normalize_embedding_input_accepts_string_list():
    assert _normalize_embedding_input(["预算审批", "合同归档"]) == ["预算审批", "合同归档"]


def test_to_base64_embedding_uses_float32_encoding():
    encoded = _to_base64_embedding([1.0, 2.0, 3.5])
    decoded = np.frombuffer(base64.b64decode(encoded), dtype=np.float32)
    assert decoded.tolist() == [1.0, 2.0, 3.5]


def test_create_embeddings_payload_returns_openai_shape():
    embedder = Mock(return_value=[[0.1, 0.2], [0.3, 0.4]])

    payload = create_embeddings_payload(
        model="bge-m3",
        input_value=["预算审批", "合同归档"],
        encoding_format="base64",
        embedder=embedder,
    )

    assert payload["object"] == "list"
    assert payload["model"] == "bge-m3"
    assert len(payload["data"]) == 2
    assert payload["data"][0]["object"] == "embedding"
    assert payload["data"][0]["index"] == 0
    assert isinstance(payload["data"][0]["embedding"], str)
    assert payload["usage"]["prompt_tokens"] == 2
    assert payload["usage"]["total_tokens"] == 2


def test_create_embeddings_payload_supports_float_output():
    embedder = Mock(return_value=[[0.1, 0.2]])

    payload = create_embeddings_payload(
        model="bge-m3",
        input_value="预算审批",
        encoding_format="float",
        embedder=embedder,
    )

    assert payload["data"][0]["embedding"] == [0.1, 0.2]
