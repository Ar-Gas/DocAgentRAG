import asyncio
import os
import sys

from starlette.requests import Request

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
