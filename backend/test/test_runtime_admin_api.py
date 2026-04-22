import os
import sys

from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.admin as admin_api  # noqa: E402
import main as main_module  # noqa: E402
from main import app  # noqa: E402


def test_runtime_health_endpoint_returns_liveness_and_readiness(monkeypatch):
    class FakeEmbeddingRuntime:
        async def health(self):
            return {"status": "degraded", "liveness": "up", "readiness": "unready"}

    class FakeDocumentService:
        def get_runtime_health(self):
            return {"rag_circuit": {"open": True, "failure_count": 3}}

    monkeypatch.setattr(admin_api, "local_embedding_runtime", FakeEmbeddingRuntime(), raising=False)
    monkeypatch.setattr(admin_api, "document_service", FakeDocumentService(), raising=False)
    monkeypatch.setattr(main_module, "ensure_internal_runtimes", lambda: None, raising=False)
    monkeypatch.setattr(main_module, "refresh_document_audit_state", lambda register_local_only=True: None, raising=False)
    monkeypatch.setattr(main_module, "run_startup_reconciliation", lambda **kwargs: None, raising=False)

    client = TestClient(app)
    response = client.get("/api/v1/admin/runtime/health")

    assert response.status_code == 200
    assert response.json()["data"]["dependencies"]["local_embedding"]["readiness"] == "unready"
    assert response.json()["data"]["rag_circuit"]["open"] is True


def test_runtime_retry_rag_endpoint_requeues_only_rag_stage(monkeypatch):
    called = {}

    class FakeDocumentService:
        def retry_rag_stage(self, document_id: str):
            called["document_id"] = document_id
            return {"document_id": document_id, "rag_ingest": "queued"}

    monkeypatch.setattr(admin_api, "document_service", FakeDocumentService(), raising=False)

    client = TestClient(app)
    response = client.post("/api/v1/admin/runtime/documents/doc-1/retry-rag")

    assert response.status_code == 200
    assert called["document_id"] == "doc-1"
    assert response.json()["data"]["rag_ingest"] == "queued"
