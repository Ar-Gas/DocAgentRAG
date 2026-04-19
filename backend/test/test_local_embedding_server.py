import os
import sys

from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_embedding_server  # noqa: E402


def test_health_check_reports_local_model():
    client = TestClient(local_embedding_server.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["model"] == "bge-m3"


def test_embeddings_endpoint_returns_openai_payload(monkeypatch):
    monkeypatch.setattr(
        local_embedding_server,
        "create_embeddings_payload",
        lambda **kwargs: {
            "object": "list",
            "model": kwargs["model"],
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        },
    )
    client = TestClient(local_embedding_server.app)

    response = client.post(
        "/v1/embeddings",
        json={"model": "bge-m3", "input": "预算审批", "encoding_format": "float"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert payload["model"] == "bge-m3"
    assert payload["data"][0]["embedding"] == [0.1, 0.2]


def test_embeddings_endpoint_rejects_wrong_dimensions():
    client = TestClient(local_embedding_server.app)

    response = client.post(
        "/v1/embeddings",
        json={"model": "bge-m3", "input": "预算审批", "dimensions": 512},
    )

    assert response.status_code == 400
    assert "1024" in response.json()["detail"]
