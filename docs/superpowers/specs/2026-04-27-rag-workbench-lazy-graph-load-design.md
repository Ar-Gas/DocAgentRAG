# RAG Workbench Lazy Graph Load Design

## Context

The current RAG workbench page embeds the LightRAG WebUI through an iframe and lets the upstream app boot with its default graph settings. In the current LightRAG WebUI bundle, the persisted default state uses:

- `queryLabel = "*"`
- `graphMaxNodes = 1000`

When the iframe boots, the WebUI immediately requests the global graph and renders a large graph snapshot. In the current runtime this produces:

- a LightRAG WebUI bundle of roughly 3.7 MB
- a graph payload of roughly 1.65 MB
- `1000` nodes and `2023` edges in the default global graph response

Backend latency for the graph endpoint is acceptable, but the combined frontend startup and graph rendering cost makes the workbench feel slow and often appear stuck in loading.

## Problem

The current first-load behavior is too heavy for the default workbench path:

- entering the page triggers a global graph fetch even when the user has not asked for a graph
- the default graph size is too large for a first paint path
- the heavy path runs inside an iframe, which makes the whole workbench feel slower than the backend actually is

## Goals

- Make the workbench open quickly without automatically fetching the global graph
- Keep the existing iframe-based LightRAG workbench architecture
- Preserve user-driven graph exploration after the page loads
- Reduce the default graph node limit for first use
- Keep the existing proxy protections against oversized graph fetches

## Non-Goals

- Replacing the iframe-based LightRAG workbench with a native DocAgent page
- Forking or rebuilding the upstream LightRAG frontend source
- Changing the backend graph schema or LightRAG graph generation logic
- Removing the ability for advanced users to manually increase graph size later

## Current Architecture

- The DocAgent frontend page embeds `/api/v1/admin/lightrag/webui/` in an iframe
- The backend admin proxy rewrites LightRAG HTML and JavaScript before returning it
- The upstream LightRAG WebUI persists its UI state in `localStorage` under `settings-storage`
- The upstream persisted default state uses `queryLabel="*"` for the initial graph page
- The upstream graph page skips graph fetching when `queryLabel` is empty, even though the lower-level fetch helper can still fall back to `label="*"`
- The DocAgent proxy already normalizes graph requests and caps oversized `max_nodes`

## Proposed Approach

### 1. Keep the iframe shell unchanged

The DocAgent page at `/rag-studio` remains an iframe wrapper. The optimization happens in the backend proxy layer so the user-facing route structure stays stable.

### 2. Inject bootstrap state into the proxied LightRAG HTML

The backend HTML sanitizer will inject a small bootstrap script into the proxied LightRAG WebUI HTML before the upstream bundle executes.

The script will:

- read `localStorage["settings-storage"]`
- parse the persisted state if present
- normalize only the graph-related defaults needed for fast first load
- write the updated value back before the LightRAG bundle initializes

### 3. Force a lazy default graph state

The bootstrap script will set the following defaults when the stored state is missing or still at the upstream global-graph default:

- `queryLabel = ""`
- `graphMaxNodes = 300`

The script will only override the query label when it is absent or equal to the upstream default global label (`"*"`). It will not clear a user-selected concrete label.

The script will only reduce the default node count when:

- no stored value exists, or
- the stored value is greater than `300`

If the user has already chosen a smaller value, that smaller value remains untouched.

### 4. Reuse the upstream empty-state path

The current upstream bundle already avoids fetching graph data when `queryLabel` is empty and instead creates an empty graph state. This behavior will be used directly rather than patched deeper in the graph-fetching logic.

This keeps the customization shallow and reduces coupling to the minified upstream bundle internals.

### 5. Keep the proxy-side graph cap

The existing admin proxy request normalization remains in place:

- user-requested graph sizes within limits are preserved
- oversized `max_nodes` values are capped server-side

This keeps first-load behavior light while still protecting the backend and browser from accidental oversized requests later.

## User Experience

### First visit

- The workbench iframe opens quickly
- No global graph request is triggered on initial page entry
- The graph panel shows the upstream empty-state prompt
- The default node limit is `300`

### Returning visit

- If the user previously selected a concrete label, that label is preserved
- If the user previously chose a smaller node limit, that smaller limit is preserved
- If the stored state still reflects the upstream default global graph, it is normalized back to the lazy defaults

### Active usage

- When the user searches or selects a label, the graph loads normally
- If the user manually increases node count later, that remains allowed up to the backend cap

## Detailed Backend Changes

### File

- `backend/api/admin.py`

### Changes

- Extend `_sanitize_lightrag_webui_html` to inject a bootstrap script before `</head>`
- Add constants for the lazy-load defaults:
  - default lazy query label: `""`
  - default lazy max nodes: `300`
- Keep the existing request normalization for `/graphs`

The injected script should be short, synchronous, and defensive:

- wrap storage access in `try/catch`
- no-op if parsing fails
- rewrite only the known shape under `settings-storage.state`
- avoid touching unrelated persisted settings

## Error Handling

- If `localStorage` is unavailable or malformed, the page falls back to current behavior
- If the upstream `settings-storage` structure changes, the bootstrap script should fail safely and leave the page functional
- The backend proxy must never fail the whole workbench response because the bootstrap injection cannot parse client-side state

## Testing Strategy

### Proxy unit tests

Add or update tests around the admin WebUI proxy to verify:

- the proxied HTML contains the injected bootstrap script
- the script references `settings-storage`
- the script sets `queryLabel` to empty
- the script sets the default max nodes to `300`
- the existing graph request cap behavior still works

### Runtime verification

Verify with live requests that:

- `/api/v1/admin/lightrag/webui/` returns injected HTML
- opening the workbench no longer immediately triggers `/graphs?label=*`
- selecting a label still triggers `/graphs?...`
- the graph endpoint still returns normally through the proxy

### Regression verification

Verify that:

- the iframe workbench still opens successfully
- graph requests still proxy correctly
- existing streaming proxy behavior remains unaffected
- existing document proxy behavior remains unaffected

## Risks and Mitigations

### Risk: upstream LightRAG changes persisted state format

Mitigation:

- keep the injection narrowly scoped
- fail open if parsing or rewrite assumptions do not hold

### Risk: user confusion on first load because no graph appears automatically

Mitigation:

- rely on the upstream empty-state guidance
- if needed later, add a DocAgent-side note near the iframe entry point without changing this design

### Risk: `300` is still too large for weaker clients

Mitigation:

- keep the value centralized in the proxy code for later tuning
- preserve any user-selected smaller value

## Rollout

1. Add the HTML bootstrap injection
2. Add proxy tests for the new injected behavior
3. Restart the backend API
4. Verify the workbench no longer triggers the default global graph request on first entry

## Acceptance Criteria

- Entering `/rag-studio` does not automatically fetch the global `label="*"` graph on a fresh default state
- The proxied LightRAG workbench still opens successfully in the iframe
- User-driven label selection still loads graphs correctly
- Default graph node count is reduced to `300` unless the user already stored a smaller value
- Server-side graph request capping still protects against oversized `max_nodes` values
