import asyncio
import importlib
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.errors import AppServiceError  # noqa: E402


def test_config_reads_lightrag_values_from_env(monkeypatch):
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
    monkeypatch.setenv("LIGHTRAG_API_KEY", "secret-key")
    monkeypatch.setenv("LIGHTRAG_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("LIGHTRAG_ENABLED", "true")

    import config

    importlib.reload(config)

    assert config.LIGHTRAG_BASE_URL == "http://127.0.0.1:9621"
    assert config.LIGHTRAG_API_KEY == "secret-key"
    assert config.LIGHTRAG_TIMEOUT_SECONDS == 12.0
    assert config.LIGHTRAG_ENABLED is True


def test_upload_file_uses_x_api_key_and_returns_payload(monkeypatch, tmp_path):
    calls = {}
    source_file = tmp_path / "budget.pdf"
    source_file.write_bytes(b"%PDF-1.4")

    class FakeResponse:
        status_code = 200
        text = '{"status":"success"}'

        def json(self):
            return {"status": "success", "track_id": "track-1", "message": "accepted"}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None):
            calls["request"] = {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "files": files,
            }
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", FakeAsyncClient)
    client = client_module.LightRAGClient(
        base_url="http://127.0.0.1:9621",
        api_key="secret-key",
        timeout_seconds=12,
    )

    payload = asyncio.run(client.upload_file(str(source_file), "预算.pdf"))

    assert payload == {"status": "success", "track_id": "track-1", "message": "accepted"}
    assert calls["init"]["timeout"] == 12
    assert calls["request"]["method"] == "POST"
    assert calls["request"]["url"] == "http://127.0.0.1:9621/documents/upload"
    assert calls["request"]["headers"]["X-API-Key"] == "secret-key"
    assert calls["request"]["files"]["file"][0] == "预算.pdf"


def test_track_status_requests_official_endpoint(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200
        text = '{"status":"processing"}'

        def json(self):
            return {"status": "processing", "documents": []}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None):
            calls["request"] = {"method": method, "url": url, "headers": headers}
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    client = client_module.LightRAGClient(base_url="http://127.0.0.1:9621", api_key="")

    payload = asyncio.run(client.get_track_status("track-1"))

    assert payload["status"] == "processing"
    assert calls["request"]["method"] == "GET"
    assert calls["request"]["url"] == "http://127.0.0.1:9621/documents/track_status/track-1"
    assert calls["request"]["headers"] == {}


def test_reprocess_failed_posts_official_endpoint(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200
        text = '{"status":"reprocessing_started"}'

        def json(self):
            return {"status": "reprocessing_started", "message": "started", "track_id": ""}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None):
            calls["request"] = {"method": method, "url": url, "headers": headers}
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    client = client_module.LightRAGClient(base_url="http://127.0.0.1:9621", api_key="")

    payload = asyncio.run(client.reprocess_failed_documents())

    assert payload["status"] == "reprocessing_started"
    assert calls["request"]["method"] == "POST"
    assert calls["request"]["url"] == "http://127.0.0.1:9621/documents/reprocess_failed"


def test_query_data_posts_expected_payload(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200
        text = '{"status":"success"}'

        def json(self):
            return {"status": "success", "data": {"chunks": []}}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None, params=None):
            calls["request"] = {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "params": params,
            }
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    client = client_module.LightRAGClient(base_url="http://127.0.0.1:9621", api_key="secret-key")

    payload = asyncio.run(client.query_data("预算审批", mode="hybrid", top_k=5))

    assert payload["status"] == "success"
    assert calls["request"]["method"] == "POST"
    assert calls["request"]["url"] == "http://127.0.0.1:9621/query/data"
    assert calls["request"]["headers"]["X-API-Key"] == "secret-key"
    assert calls["request"]["json"] == {"query": "预算审批", "mode": "hybrid", "top_k": 5}


def test_graph_endpoints_use_expected_paths(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = '{"status":"success"}'

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None, params=None):
            calls.append({"method": method, "url": url, "params": params})
            if url.endswith("/graph/label/list"):
                return FakeResponse({"labels": ["财务管理"]})
            return FakeResponse({"nodes": [], "edges": []})

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    client = client_module.LightRAGClient(base_url="http://127.0.0.1:9621", api_key="")

    labels = asyncio.run(client.list_graph_labels())
    graph = asyncio.run(client.get_graph("财务管理", max_depth=2, max_nodes=50))

    assert labels["labels"] == ["财务管理"]
    assert graph["nodes"] == []
    assert calls[0]["url"] == "http://127.0.0.1:9621/graph/label/list"
    assert calls[1]["url"] == "http://127.0.0.1:9621/graphs"
    assert calls[1]["params"] == {"label": "财务管理", "max_depth": 2, "max_nodes": 50}


def test_non_2xx_response_becomes_app_service_error(monkeypatch):
    class FakeResponse:
        status_code = 503
        text = "upstream failed"

        def json(self):
            return {"detail": "upstream failed"}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None, files=None):
            return FakeResponse()

    import app.infra.lightrag_client as client_module

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())
    client = client_module.LightRAGClient(base_url="http://127.0.0.1:9621", api_key="")

    try:
        asyncio.run(client.health())
    except AppServiceError as exc:
        assert exc.code == 4001
        assert "LightRAG returned 503" in exc.detail
        assert "upstream failed" in exc.detail
    else:
        raise AssertionError("expected AppServiceError")
