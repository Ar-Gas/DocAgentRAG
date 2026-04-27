import asyncio
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
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


def _extract_lazy_bootstrap_javascript() -> str:
    script_html = admin_api._build_lightrag_lazy_graph_bootstrap_script()
    match = re.search(r"<script[^>]*>(.*)</script>", script_html, flags=re.DOTALL)
    assert match, "lazy bootstrap script tag was not found"
    return match.group(1).strip()


def _resolve_node_binary() -> str:
    env_override = os.getenv("DOCAGENT_NODE_BINARY", "").strip()
    if env_override:
        return env_override

    discovered = shutil.which("node")
    if discovered:
        return discovered

    pytest.skip("Node.js binary is unavailable; skipping bootstrap behavior tests")


def _run_lazy_bootstrap(initial_settings_storage):
    bootstrap_js = _extract_lazy_bootstrap_javascript()
    node_program = f"""
const bootstrap = {json.dumps(bootstrap_js)};
const initialStorageValue = {json.dumps(initial_settings_storage)};
const store = {{}};
const writes = [];
if (initialStorageValue !== null) {{
  store["settings-storage"] = initialStorageValue;
}}

global.window = {{
  localStorage: {{
    getItem(key) {{
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    }},
    setItem(key, value) {{
      store[key] = value;
      writes.push([key, value]);
    }},
  }},
}};

eval(bootstrap);

process.stdout.write(JSON.stringify({{
  settingsStorage: Object.prototype.hasOwnProperty.call(store, "settings-storage")
    ? store["settings-storage"]
    : null,
  writes,
}}));
""".strip()
    completed = subprocess.run(
        [_resolve_node_binary(), "-e", node_program],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_resolve_node_binary_prefers_env_override(monkeypatch):
    monkeypatch.setenv("DOCAGENT_NODE_BINARY", "/tmp/custom-node")
    assert _resolve_node_binary() == "/tmp/custom-node"


def test_resolve_node_binary_skips_when_unavailable(monkeypatch):
    monkeypatch.delenv("DOCAGENT_NODE_BINARY", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.skip.Exception):
        _resolve_node_binary()


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


def test_proxy_lightrag_webui_html_bootstrap_seeds_defaults_without_existing_storage(monkeypatch):
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
    assert "if (!raw) return;" not in body
    assert "const payload = raw ? JSON.parse(raw) : {};" in body
    assert "const state = {};" in body
    assert "if (changed) {" in body
    assert "window.localStorage.setItem(storageKey, JSON.stringify(" in body


def test_lazy_bootstrap_seeds_first_visit_defaults_behavior():
    outcome = _run_lazy_bootstrap(None)

    assert len(outcome["writes"]) == 1
    payload = json.loads(outcome["settingsStorage"])
    assert payload["state"]["queryLabel"] == ""
    assert payload["state"]["graphMaxNodes"] == 300


def test_lazy_bootstrap_preserves_concrete_label_and_smaller_max_nodes_behavior():
    existing = json.dumps({"state": {"queryLabel": "project-docs", "graphMaxNodes": 120}})
    outcome = _run_lazy_bootstrap(existing)

    assert outcome["writes"] == []
    assert outcome["settingsStorage"] == existing


def test_lazy_bootstrap_rewrites_global_label_and_oversized_max_nodes_behavior():
    existing = json.dumps({"state": {"queryLabel": "*", "graphMaxNodes": 999}})
    outcome = _run_lazy_bootstrap(existing)

    assert len(outcome["writes"]) == 1
    payload = json.loads(outcome["settingsStorage"])
    assert payload["state"]["queryLabel"] == ""
    assert payload["state"]["graphMaxNodes"] == 300


def test_lazy_bootstrap_handles_string_state_and_blank_max_nodes_behavior():
    existing_state = json.dumps({"queryLabel": "engineering", "graphMaxNodes": "   "})
    existing = json.dumps({"state": existing_state})
    outcome = _run_lazy_bootstrap(existing)

    assert len(outcome["writes"]) == 1
    payload = json.loads(outcome["settingsStorage"])
    assert isinstance(payload["state"], str)
    parsed_state = json.loads(payload["state"])
    assert parsed_state["queryLabel"] == "engineering"
    assert parsed_state["graphMaxNodes"] == 300


def test_lazy_bootstrap_fail_open_on_invalid_storage_payload_behavior():
    invalid_payload = "{invalid-json"
    outcome = _run_lazy_bootstrap(invalid_payload)

    assert outcome["writes"] == []
    assert outcome["settingsStorage"] == invalid_payload


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
