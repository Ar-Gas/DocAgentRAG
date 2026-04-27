# RAG Workbench Lazy Graph Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `/rag-studio` from auto-fetching the global LightRAG graph on first load by bootstrapping lazy graph defaults in the proxied WebUI HTML while preserving user-selected labels and smaller node limits.

**Architecture:** Keep the existing iframe wrapper unchanged and modify only the backend LightRAG HTML proxy. Inject a small inline bootstrap script into the proxied LightRAG HTML before the upstream bundle initializes so `settings-storage.state.queryLabel` defaults to empty and `graphMaxNodes` defaults to `300`. Lock the behavior with focused proxy unit tests, then verify at runtime that first entry no longer triggers `label=*`.

**Tech Stack:** FastAPI, Python, pytest, Starlette Request/Response, LightRAG WebUI HTML proxy rewriting

---

## File Structure

- Modify: `backend/api/admin.py`
  - Responsibility: build and inject the lazy graph bootstrap script into proxied LightRAG HTML, keep existing `/graphs` request normalization unchanged.
- Modify: `backend/test/test_lightrag_webui_proxy_api.py`
  - Responsibility: proxy contract tests for lazy graph bootstrap HTML injection and graph request normalization.
- Inspect only: `frontend/docagent-frontend/src/pages/RagStudioPage.vue`
  - Responsibility: confirm the iframe shell remains unchanged so the scope stays in the backend proxy.

## Task 1: Lock the Lazy Bootstrap HTML Contract

**Files:**
- Modify: `backend/test/test_lightrag_webui_proxy_api.py`
- Test: `backend/test/test_lightrag_webui_proxy_api.py`

- [ ] **Step 1: Write the failing tests**

Add these tests near the existing WebUI HTML proxy tests in `backend/test/test_lightrag_webui_proxy_api.py`:

```python
def test_proxy_lightrag_webui_html_injects_lazy_graph_bootstrap_defaults(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == ""
        return _FakeResponse(
            content=(
                b'<html><head><title>Lightrag</title>'
                b'<script type="module" src="/webui/assets/index.js"></script>'
                b'<link rel="stylesheet" href="/webui/assets/index.css"></head>'
                b'<body>LightRAG</body></html>'
            ),
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_webui_root(_request("/api/v1/admin/lightrag/webui/"))
    )

    body = response.body.decode("utf-8")
    assert 'data-docagent-lazy-graph-bootstrap' in body
    assert 'const storageKey = "settings-storage"' in body
    assert 'const defaultQueryLabel = ""' in body
    assert 'const defaultMaxNodes = 300' in body


def test_proxy_lightrag_webui_html_bootstrap_only_rewrites_global_defaults(monkeypatch):
    async def fake_proxy(base_path="webui", path="", query="", method="GET", body=b"", content_type=None):
        assert base_path == "webui"
        assert path == ""
        return _FakeResponse(
            content=(
                b'<html><head><title>Lightrag</title></head>'
                b'<body><div id="root"></div></body></html>'
            ),
        )

    monkeypatch.setattr(admin_api, "_proxy_lightrag_webui_request", fake_proxy)

    response = asyncio.run(
        admin_api.proxy_lightrag_webui_root(_request("/api/v1/admin/lightrag/webui/"))
    )

    body = response.body.decode("utf-8")
    assert 'currentQueryLabel === "*"' in body
    assert 'state.queryLabel = defaultQueryLabel' in body
    assert 'currentMaxNodes > defaultMaxNodes' in body
    assert 'window.localStorage.setItem(' in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
backend/.venv/bin/python -m pytest backend/test/test_lightrag_webui_proxy_api.py -q
```

Expected:

```text
FAIL ... test_proxy_lightrag_webui_html_injects_lazy_graph_bootstrap_defaults
AssertionError: assert 'data-docagent-lazy-graph-bootstrap' in body
```

- [ ] **Step 3: Write the minimal implementation**

Update `backend/api/admin.py` to add a dedicated bootstrap helper and inject it before the existing API-tab hiding script:

```python
import json
import os
from urllib.parse import parse_qsl, urlencode

LIGHTRAG_LAZY_GRAPH_QUERY_LABEL = ""
LIGHTRAG_LAZY_GRAPH_DEFAULT_MAX_NODES = 300


def _build_lightrag_lazy_graph_bootstrap_script() -> str:
    return f"""
<script data-docagent-lazy-graph-bootstrap>
  (() => {{
    const storageKey = "settings-storage";
    const defaultQueryLabel = {json.dumps(LIGHTRAG_LAZY_GRAPH_QUERY_LABEL)};
    const defaultMaxNodes = {LIGHTRAG_LAZY_GRAPH_DEFAULT_MAX_NODES};
    try {{
      const raw = window.localStorage.getItem(storageKey);
      const payload = raw ? JSON.parse(raw) : {{}};
      const basePayload = payload && typeof payload === "object" ? payload : {{}};
      const baseState =
        basePayload.state && typeof basePayload.state === "object"
          ? basePayload.state
          : {{}};
      const state = {{ ...baseState }};
      let changed = false;

      const hasStoredQueryLabel = typeof state.queryLabel === "string";
      const currentQueryLabel = hasStoredQueryLabel ? state.queryLabel.trim() : "";
      if (!hasStoredQueryLabel || currentQueryLabel === "*") {{
        if (state.queryLabel !== defaultQueryLabel) {{
          state.queryLabel = defaultQueryLabel;
          changed = true;
        }}
      }}

      const currentMaxNodes = Number(state.graphMaxNodes);
      if (!Number.isFinite(currentMaxNodes) || currentMaxNodes > defaultMaxNodes) {{
        if (state.graphMaxNodes !== defaultMaxNodes) {{
          state.graphMaxNodes = defaultMaxNodes;
          changed = true;
        }}
      }}

      if (!changed) {{
        return;
      }}

      window.localStorage.setItem(
        storageKey,
        JSON.stringify({{ ...basePayload, state }})
      );
    }} catch (_) {{
      // Fall back to upstream defaults if persisted state is unavailable.
    }}
  }})();
</script>
""".strip()


def _sanitize_lightrag_webui_html(raw_html: str) -> str:
    sanitized = _rewrite_lightrag_branding(raw_html)
    sanitized = sanitized.replace(
        'src="/webui/',
        f'src="{LIGHTRAG_WEBUI_PROXY_PREFIX}/',
    ).replace(
        'href="/webui/',
        f'href="{LIGHTRAG_WEBUI_PROXY_PREFIX}/',
    ).replace(
        'src="logo.svg"',
        'src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="',
    ).replace(
        'href="favicon.png"',
        'href="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="',
    )
    injection = "\n".join(
        [
            _build_lightrag_lazy_graph_bootstrap_script(),
            """
<style data-docagent-hide-api-tab>
  a[href*="github.com"],
  a[href*="HKUDS"],
  a[href="#"],
  [class*="footer"],
  [id*="footer"],
  iframe.api-docs-iframe,
  [class*="api-docs"],
  [id*="api-docs"] {
    display: none !important;
  }
</style>
<script data-docagent-hide-api-tab>
  (() => {
    const hideApiEntry = () => {
      const candidates = Array.from(document.querySelectorAll('a, button, [role="tab"], [data-state], [class]'));
      for (const node of candidates) {
        const text = (node.textContent || '').trim().toLowerCase();
        const href = (node.getAttribute && (node.getAttribute('href') || node.getAttribute('to') || '')) || '';
        if (text === 'api' || href.includes('api')) {
          node.style.display = 'none';
          node.setAttribute('aria-hidden', 'true');
        }
      }
    };
    hideApiEntry();
    new MutationObserver(hideApiEntry).observe(document.documentElement, { childList: true, subtree: true });
  })();
</script>
""".strip(),
        ]
    )
    if "</head>" in sanitized:
        sanitized = sanitized.replace("</head>", f"{injection}</head>", 1)
    return sanitized
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
backend/.venv/bin/python -m pytest backend/test/test_lightrag_webui_proxy_api.py -q
```

Expected:

```text
...........
[100%]
```

- [ ] **Step 5: Commit**

Run:

```bash
git add backend/api/admin.py backend/test/test_lightrag_webui_proxy_api.py
git commit -m "feat: lazy-load default lightrag graph"
```

## Task 2: Prove the Workbench No Longer Auto-Fetches the Global Graph

**Files:**
- Modify: none
- Test: `backend/test/test_lightrag_webui_proxy_api.py`

- [ ] **Step 1: Restart the API with the new proxy code**

Run:

```bash
backend/.venv/bin/python backend/scripts/dev_supervisor.py restart api
```

Expected:

```text
[docagent] started api pid=<pid> log=/home/zyq/DocAgentRAG/logs/api/current.log
[docagent] api healthy: http://127.0.0.1:6008/health
```

- [ ] **Step 2: Fetch the proxied HTML and verify the bootstrap script is present**

Run:

```bash
python3 - <<'PY'
import urllib.request

html = urllib.request.urlopen(
    "http://127.0.0.1:6008/api/v1/admin/lightrag/webui/",
    timeout=10,
).read().decode("utf-8", "ignore")

assert 'data-docagent-lazy-graph-bootstrap' in html
assert 'const storageKey = "settings-storage"' in html
assert 'const defaultQueryLabel = ""' in html
assert 'const defaultMaxNodes = 300' in html
print("bootstrap-ok")
PY
```

Expected:

```text
bootstrap-ok
```

- [ ] **Step 3: Open the workbench and verify first entry does not trigger the global graph**

Open this page in the browser:

```text
http://127.0.0.1:3000/rag-studio
```

Then hard-refresh once and inspect the iframe network activity or API log.

Expected:

```text
No immediate GET /api/v1/admin/lightrag/app/graphs?label=* request appears on first entry.
The iframe opens and the graph panel shows the upstream empty-state prompt.
```

- [ ] **Step 4: Trigger a user-driven graph load and verify the proxy still works**

Inside the LightRAG workbench:

```text
1. Search or select a concrete graph label.
2. Load the graph from the WebUI.
3. Confirm a GET /api/v1/admin/lightrag/app/graphs?label=<selected>... request appears.
```

Expected:

```text
The selected graph loads normally and no backend proxy error is shown.
```

- [ ] **Step 5: Run the focused regression checks**

Run:

```bash
backend/.venv/bin/python -m pytest backend/test/test_lightrag_webui_proxy_api.py -q
backend/.venv/bin/python backend/scripts/dev_supervisor.py status api
```

Expected:

```text
All proxy tests pass.
api: pid=<pid> port=6008 healthy http://127.0.0.1:6008/health
```
