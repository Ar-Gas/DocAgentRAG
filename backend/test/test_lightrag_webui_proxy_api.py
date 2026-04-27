import asyncio
import os
import sys

from starlette.requests import Request
from starlette.responses import StreamingResponse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.admin as admin_api  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code=200, content=b"<html>LightRAG</html>", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}


def _request(path: str):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def _request_with_query(path: str, query_string: str):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": [],
    }
    return Request(scope)


def _request_with_receive(path: str, method: str = "GET", body: bytes = b"", headers=None):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
    }

    received = {"done": False}

    async def receive():
        if not received["done"]:
            received["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return Request(scope, receive)


def test_proxy_lightrag_webui_rewrites_root_html_and_hides_branding(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == ""
        return _FakeResponse(
            content=(
                b'<html><head><title>Lightrag</title>'
                b'<script type="module" src="/webui/assets/index.js"></script>'
                b'<link rel="stylesheet" href="/webui/assets/index.css"></head>'
                b'<body>LightRAG<a href="https://github.com/HKUDS/LightRAG">repo</a></body></html>'
            ),
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(admin_api.proxy_lightrag_webui_root(_request("/api/v1/admin/lightrag/webui/")))

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "DocAgent Studio" in body
    assert "/api/v1/admin/lightrag/webui/assets/index.js" in body
    assert "/api/v1/admin/lightrag/webui/assets/index.css" in body
    assert "LightRAG" not in body
    assert "data-docagent-hide-api-tab" in body


def test_proxy_lightrag_webui_html_injects_lazy_graph_bootstrap_defaults(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == ""
        return _FakeResponse(
            content=(
                b'<html><head><script type="module" src="/webui/assets/index.js"></script>'
                b'<link rel="stylesheet" href="/webui/assets/index.css"></head>'
                b"<body><div id=\"root\"></div></body></html>"
            ),
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(admin_api.proxy_lightrag_webui_root(_request("/api/v1/admin/lightrag/webui/")))

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "data-docagent-lazy-graph-bootstrap" in body
    assert 'const storageKey = "settings-storage"' in body
    assert 'const defaultQueryLabel = ""' in body
    assert "const defaultMaxNodes = 300" in body


def test_proxy_lightrag_webui_html_bootstrap_only_rewrites_global_defaults(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == ""
        return _FakeResponse(
            content=b"<html><head></head><body><div id=\"root\"></div></body></html>",
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(admin_api.proxy_lightrag_webui_root(_request("/api/v1/admin/lightrag/webui/")))

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert 'currentQueryLabel === "*"' in body
    assert "state.queryLabel = defaultQueryLabel" in body
    assert "currentMaxNodes > defaultMaxNodes" in body
    assert "window.localStorage.setItem(" in body


def test_proxy_lightrag_webui_nested_path_preserves_content_type(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == "assets/app.js"
        return _FakeResponse(
            status_code=200,
            content=b"console.log('ok')",
            headers={"content-type": "application/javascript"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(admin_api.proxy_lightrag_webui_path("assets/app.js", _request("/api/v1/admin/lightrag/webui/assets/app.js")))

    assert response.status_code == 200
    assert response.media_type == "application/javascript"
    assert response.body == b"console.log('ok')"


def test_proxy_lightrag_webui_js_rewrites_api_base_and_home_link(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == "assets/index.js"
        return _FakeResponse(
            status_code=200,
            content=(
                b'const Fh="",dW="/webui/",'
                b'lA={name:"LightRAG",github:"https://github.com/HKUDS/LightRAG"};'
                b'const title="LightRAG";'
            ),
            headers={"content-type": "application/javascript"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_webui_path(
            "assets/index.js",
            _request("/api/v1/admin/lightrag/webui/assets/index.js"),
        )
    )

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert 'Fh="/api/v1/admin/lightrag/app"' in body
    assert 'dW="/api/v1/admin/lightrag/webui/"' in body
    assert "DocAgent Studio" in body
    assert "LightRAG" not in body
    assert "api:!1" in body or '"api":!1' in body


def test_proxy_lightrag_webui_js_rewrites_minified_assignment_form(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == "assets/index.js"
        return _FakeResponse(
            status_code=200,
            content=(
                b'const x=1,Fh="",dW="/webui/",lA={name:"LightRAG",github:"https://github.com/HKUDS/LightRAG"};'
                b'Bn=Dn.create({baseURL:Fh,headers:{"Content-Type":"application/json"}});'
                b'Dn.get("/auth-status",{baseURL:Fh});'
            ),
            headers={"content-type": "application/javascript"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_webui_path(
            "assets/index.js",
            _request("/api/v1/admin/lightrag/webui/assets/index.js"),
        )
    )

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert 'Fh="/api/v1/admin/lightrag/app"' in body
    assert 'baseURL:Fh' in body
    assert 'Dn.get("/auth-status",{baseURL:Fh})' in body


def test_proxy_lightrag_webui_js_suppresses_truncation_toast(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == "assets/index.js"
        return _FakeResponse(
            status_code=200,
            content=(
                b'const x=1;'
                b'R?.is_truncated&&Kt.info(e("graphPanel.dataIsTruncated","Graph data is truncated to Max Nodes"));'
                b'const y=2;'
            ),
            headers={"content-type": "application/javascript"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_webui_path(
            "assets/index.js",
            _request("/api/v1/admin/lightrag/webui/assets/index.js"),
        )
    )

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "graphPanel.dataIsTruncated" not in body
    assert 'console.info("DocAgent graph truncated")' in body


def test_proxy_lightrag_query_stream_uses_streaming_proxy(monkeypatch):
    calls = {"stream": 0, "regular": 0}

    async def fake_stream_proxy(path="", query="", method="GET", body=b"", content_type=None):
        calls["stream"] += 1
        assert path == "query/stream"
        assert method == "POST"
        assert content_type == "application/json"

        async def fake_body():
            yield b'{"response":"ok"}\n'

        return StreamingResponse(fake_body(), media_type="application/x-ndjson")

    async def fake_proxy(base_path="", path="", query="", method="GET", body=b"", content_type=None):
        calls["regular"] += 1
        return _FakeResponse(
            status_code=200,
            content=b'{"response":"wrong"}',
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_stream_request", fake_stream_proxy, raising=False)
    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_app_path(
            "query/stream",
            _request_with_receive(
                "/api/v1/admin/lightrag/app/query/stream",
                method="POST",
                body=b'{"query":"test"}',
                headers=[(b"content-type", b"application/json")],
            ),
        )
    )

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/x-ndjson"
    assert calls == {"stream": 1, "regular": 0}


def test_proxy_lightrag_graphs_preserves_requested_max_nodes_within_limit(monkeypatch):
    captured = {}

    async def fake_proxy(base_path="", path="", query="", method="GET", body=b"", content_type=None):
        captured["path"] = path
        captured["query"] = query
        return _FakeResponse(
            status_code=200,
            content=b'{"nodes":[],"edges":[],"is_truncated":false}',
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_app_path(
            "graphs",
            _request_with_query(
                "/api/v1/admin/lightrag/app/graphs",
                "label=%2A&max_depth=3&max_nodes=1000",
            ),
        )
    )

    assert response.status_code == 200
    assert captured["path"] == "graphs"
    assert "max_nodes=1000" in captured["query"]
    assert "max_nodes=5000" not in captured["query"]


def test_proxy_lightrag_graphs_caps_oversized_max_nodes(monkeypatch):
    captured = {}

    async def fake_proxy(base_path="", path="", query="", method="GET", body=b"", content_type=None):
        captured["path"] = path
        captured["query"] = query
        return _FakeResponse(
            status_code=200,
            content=b'{"nodes":[],"edges":[],"is_truncated":false}',
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_app_path(
            "graphs",
            _request_with_query(
                "/api/v1/admin/lightrag/app/graphs",
                "label=%2A&max_depth=3&max_nodes=8000",
            ),
        )
    )

    assert response.status_code == 200
    assert captured["path"] == "graphs"
    assert "max_nodes=5000" in captured["query"]
    assert "max_nodes=8000" not in captured["query"]


def test_proxy_lightrag_reprocess_failed_ensures_local_embedding_ready(monkeypatch):
    calls = {"ensure_ready": 0, "proxy": 0}

    class FakeRuntime:
        async def ensure_ready(self):
            calls["ensure_ready"] += 1
            return {"status": "healthy"}

    async def fake_proxy(base_path="", path="", query="", method="GET", body=b"", content_type=None):
        calls["proxy"] += 1
        assert base_path == ""
        assert path == "documents/reprocess_failed"
        assert method == "POST"
        return _FakeResponse(
            status_code=200,
            content=b'{"status":"reprocessing_started"}',
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)
    monkeypatch.setattr(admin_api, "local_embedding_runtime", FakeRuntime(), raising=False)

    response = asyncio.run(
        admin_api.proxy_lightrag_app_path(
            "documents/reprocess_failed",
            _request_with_receive(
                "/api/v1/admin/lightrag/app/documents/reprocess_failed",
                method="POST",
            ),
        )
    )

    assert response.status_code == 200
    assert response.body == b'{"status":"reprocessing_started"}'
    assert calls == {"ensure_ready": 1, "proxy": 1}
