import os
import sys

from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import local_embedding_server  # noqa: E402


def test_health_check_reports_local_model():
    def fake_status():
        return {"state": "ready", "model": "bge-m3", "ready": True}

    local_embedding_server.app.dependency_overrides[local_embedding_server.get_bge_model_status] = fake_status
    client = TestClient(local_embedding_server.app)

    try:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["model"] == "bge-m3"
        assert response.json()["readiness"] == "ready"
        assert response.json()["ready"] is True
    finally:
        local_embedding_server.app.dependency_overrides.clear()


def test_health_check_reports_warming_up_before_model_loaded():
    def fake_status():
        return {"state": "unloaded", "model": "bge-m3", "ready": False}

    local_embedding_server.app.dependency_overrides[local_embedding_server.get_bge_model_status] = fake_status
    client = TestClient(local_embedding_server.app)

    try:
        response = client.get("/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "warming_up"
        assert payload["readiness"] == "warming_up"
        assert payload["ready"] is False
    finally:
        local_embedding_server.app.dependency_overrides.clear()


def test_health_check_reports_failed_model_initialization():
    def fake_status():
        return {"state": "failed", "model": "bge-m3", "ready": False, "detail": "Cannot copy out of meta tensor"}

    local_embedding_server.app.dependency_overrides[local_embedding_server.get_bge_model_status] = fake_status
    client = TestClient(local_embedding_server.app)

    try:
        response = client.get("/health")

        assert response.status_code == 503
        payload = response.json()
        assert payload["status"] == "unhealthy"
        assert payload["readiness"] == "failed"
        assert payload["ready"] is False
        assert "meta tensor" in payload["detail"]
    finally:
        local_embedding_server.app.dependency_overrides.clear()


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


def test_embeddings_endpoint_returns_clean_initialization_error(monkeypatch):
    monkeypatch.setattr(
        local_embedding_server,
        "create_embeddings_payload",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("BGE model load failed: Cannot copy out of meta tensor")),
    )
    client = TestClient(local_embedding_server.app)

    response = client.post(
        "/v1/embeddings",
        json={"model": "bge-m3", "input": "预算审批", "encoding_format": "float"},
    )

    assert response.status_code == 503
    assert "BGE model load failed" in response.json()["detail"]


def test_embeddings_endpoint_rejects_wrong_dimensions():
    original_dim = local_embedding_server.LOCAL_EMBEDDING_DIM
    original_model = local_embedding_server.LOCAL_EMBEDDING_MODEL_NAME
    local_embedding_server.LOCAL_EMBEDDING_DIM = 384
    local_embedding_server.LOCAL_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
    client = TestClient(local_embedding_server.app)

    try:
        response = client.post(
            "/v1/embeddings",
            json={"model": "all-MiniLM-L6-v2", "input": "预算审批", "dimensions": 1024},
        )

        assert response.status_code == 400
        assert "384" in response.json()["detail"]
    finally:
        local_embedding_server.LOCAL_EMBEDDING_DIM = original_dim
        local_embedding_server.LOCAL_EMBEDDING_MODEL_NAME = original_model
