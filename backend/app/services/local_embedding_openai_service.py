from __future__ import annotations

import base64
from typing import Callable, Iterable, List

import numpy as np

from app.infra.embedding_provider import get_local_embedding_model_name


def _normalize_embedding_input(input_value) -> List[str]:
    if isinstance(input_value, str):
        return [input_value]
    if isinstance(input_value, list) and all(isinstance(item, str) for item in input_value):
        return list(input_value)
    raise ValueError("input must be a string or a list of strings")


def _to_base64_embedding(values: Iterable[float]) -> str:
    buffer = np.asarray(list(values), dtype=np.float32).tobytes()
    return base64.b64encode(buffer).decode("ascii")


def create_embeddings_payload(
    *,
    model: str | None,
    input_value,
    encoding_format: str = "float",
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> dict:
    texts = _normalize_embedding_input(input_value)
    embedder = embedder or _default_embedder
    vectors = embedder(texts)
    normalized_format = (encoding_format or "float").lower()

    data = []
    for index, vector in enumerate(vectors):
        payload_vector = (
            _to_base64_embedding(vector)
            if normalized_format == "base64"
            else [float(item) for item in vector]
        )
        data.append(
            {
                "object": "embedding",
                "index": index,
                "embedding": payload_vector,
            }
        )

    return {
        "object": "list",
        "data": data,
        "model": model or get_local_embedding_model_name(),
        "usage": {
            "prompt_tokens": len(texts),
            "total_tokens": len(texts),
        },
    }


def _default_embedder(texts: list[str]) -> list[list[float]]:
    from app.infra.embedding_provider import _get_bge_ef

    results = _get_bge_ef()(texts)
    return [list(item) for item in results]
