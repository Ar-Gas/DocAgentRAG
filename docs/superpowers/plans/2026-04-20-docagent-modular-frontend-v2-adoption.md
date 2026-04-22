# DocAgent Modular Frontend V2 Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the frontend onto normalized domain-specific API clients and v2 contracts while preserving the existing user experience and allowing controlled fallback to v1 during rollout.

**Architecture:** Keep the current Vue application structure, but centralize network access into split API modules and normalize all document, retrieval, QA, graph, classification, and runtime payloads before components consume them. Add a dual-stack mode so the frontend can be validated against v2 without removing the working v1 path too early.

**Tech Stack:** Vue 3, Vite, Vitest, existing frontend test setup

---

## File Structure

**Files:**
- Create: `frontend/docagent-frontend/src/api/client.js`
- Create: `frontend/docagent-frontend/src/api/documents.js`
- Create: `frontend/docagent-frontend/src/api/retrieval.js`
- Create: `frontend/docagent-frontend/src/api/qa.js`
- Create: `frontend/docagent-frontend/src/api/classification.js`
- Create: `frontend/docagent-frontend/src/api/graph.js`
- Create: `frontend/docagent-frontend/src/api/runtime.js`
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/QAPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/GraphPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/DashboardPage.vue`
- Modify: `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`
- Create: `frontend/docagent-frontend/src/api/__tests__/v2-clients.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/DashboardPage.spec.js`

---

### Task 1: Split And Normalize The API Client Layer

**Files:**
- Create: `frontend/docagent-frontend/src/api/client.js`
- Create: `frontend/docagent-frontend/src/api/documents.js`
- Create: `frontend/docagent-frontend/src/api/retrieval.js`
- Create: `frontend/docagent-frontend/src/api/qa.js`
- Create: `frontend/docagent-frontend/src/api/classification.js`
- Create: `frontend/docagent-frontend/src/api/graph.js`
- Create: `frontend/docagent-frontend/src/api/runtime.js`
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Create: `frontend/docagent-frontend/src/api/__tests__/v2-clients.spec.js`

- [ ] **Step 1: Write the failing API client normalization tests**

Create `frontend/docagent-frontend/src/api/__tests__/v2-clients.spec.js` with:

```javascript
import { normalizeDocument } from '../documents'
import { normalizeRetrievalResult } from '../retrieval'

test('normalizeDocument exposes lifecycle status and active version', () => {
  const view = normalizeDocument({
    document_id: 'doc-1',
    filename: 'report.pdf',
    lifecycle_status: 'ready',
    active_version_id: 'ver-1'
  })

  expect(view.id).toBe('doc-1')
  expect(view.lifecycleStatus).toBe('ready')
  expect(view.activeVersionId).toBe('ver-1')
})

test('normalizeRetrievalResult exposes citation ids', () => {
  const result = normalizeRetrievalResult({
    total: 1,
    items: [{ document_id: 'doc-1', block_id: 'blk-1', content: 'federated learning', score: 0.9 }]
  })

  expect(result.items[0].documentId).toBe('doc-1')
  expect(result.items[0].blockId).toBe('blk-1')
})
```

- [ ] **Step 2: Run the API client tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm run test -- src/api/__tests__/v2-clients.spec.js`
Expected: FAIL because the split clients and normalization helpers do not exist yet.

- [ ] **Step 3: Implement the split clients**

Create `src/api/client.js` with a shared `request` helper. Implement one file per domain and export normalization helpers such as:

```javascript
export function normalizeDocument(payload) {
  return {
    id: payload.document_id ?? payload.id,
    filename: payload.filename,
    lifecycleStatus: payload.lifecycle_status ?? payload.ingest_status ?? 'unknown',
    activeVersionId: payload.active_version_id ?? null
  }
}
```

Update `src/api/index.js` to re-export the split clients and keep the old imports working.

- [ ] **Step 4: Re-run the API client tests**

Run: `cd frontend/docagent-frontend && npm run test -- src/api/__tests__/v2-clients.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the split API layer**

```bash
git add frontend/docagent-frontend/src/api
git commit -m "feat: split frontend api layer for v2 adoption"
```

### Task 2: Update Documents And Search Pages For Lifecycle State And Citations

**Files:**
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`

- [ ] **Step 1: Write the failing UI assertions**

Extend `src/pages/__tests__/SearchPage.spec.js` with:

```javascript
test('renders citation-aware search result actions', async () => {
  // mount SearchPage with mocked retrieval client returning blockId/pageNumber
  // expect the open-document action to receive the block identifier
})
```

Add a similar assertion in the documents page test suite for `lifecycleStatus`.

- [ ] **Step 2: Run the affected page tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/SearchPage.spec.js`
Expected: FAIL until the page consumes normalized v2-aware models.

- [ ] **Step 3: Implement the page updates**

Update the documents page to render `ready`, `degraded_lightrag`, and `failed_extract` explicitly. Update the search page and `DocumentViewerModal` so result clicks propagate `documentId`, `blockId`, and page or anchor metadata into the viewer.

- [ ] **Step 4: Re-run the affected page tests**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/SearchPage.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the documents and search updates**

```bash
git add frontend/docagent-frontend/src/pages/DocumentsPage.vue frontend/docagent-frontend/src/pages/SearchPage.vue frontend/docagent-frontend/src/components/DocumentViewerModal.vue frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js
git commit -m "feat: render document lifecycle and citation-aware search results"
```

### Task 3: Update QA, Graph, And Dashboard Pages For v2 Runtime Data

**Files:**
- Modify: `frontend/docagent-frontend/src/pages/QAPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/GraphPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/DashboardPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/DashboardPage.spec.js`

- [ ] **Step 1: Write the failing page assertions**

Add assertions that:

```javascript
// QAPage displays streamed citations with documentId and blockId
// GraphPage renders normalized node and edge labels from the graph client
// DashboardPage renders runtime dependency health from the runtime client
```

- [ ] **Step 2: Run the affected page tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/QAPage.spec.js src/pages/__tests__/GraphPage.spec.js src/pages/__tests__/DashboardPage.spec.js`
Expected: FAIL until the pages switch to the split clients and v2 models.

- [ ] **Step 3: Implement the page updates**

Update the QA page to consume the new QA client and preserve streaming. Update the graph page to consume normalized `nodes` and `edges`. Update the dashboard page to show runtime dependency health and audit summaries.

- [ ] **Step 4: Re-run the affected page tests**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/QAPage.spec.js src/pages/__tests__/GraphPage.spec.js src/pages/__tests__/DashboardPage.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the QA, graph, and dashboard updates**

```bash
git add frontend/docagent-frontend/src/pages/QAPage.vue frontend/docagent-frontend/src/pages/GraphPage.vue frontend/docagent-frontend/src/pages/DashboardPage.vue frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js frontend/docagent-frontend/src/pages/__tests__/DashboardPage.spec.js
git commit -m "feat: adopt v2 qa graph and runtime frontend clients"
```

### Task 4: Add Dual-Stack v1/v2 Rollout Control

**Files:**
- Modify: `frontend/docagent-frontend/src/api/client.js`
- Modify: `frontend/docagent-frontend/src/stores/app.js`
- Create: `frontend/docagent-frontend/src/composables/useApiMode.js`

- [ ] **Step 1: Write the failing rollout toggle test**

Add a small store test verifying that the selected API mode switches request prefixes between `/api/v1` and `/api/v2`.

- [ ] **Step 2: Run the toggle test and verify it fails**

Run: `cd frontend/docagent-frontend && npm run test -- src/api/__tests__/v2-clients.spec.js`
Expected: FAIL until the client respects a selected API mode.

- [ ] **Step 3: Implement the dual-stack mode**

Add a shared API mode source, default it to `v1` for safety, and allow page-level experimentation with `v2`. Route each domain client through the selected prefix.

- [ ] **Step 4: Re-run the toggle test**

Run: `cd frontend/docagent-frontend && npm run test -- src/api/__tests__/v2-clients.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the rollout toggle**

```bash
git add frontend/docagent-frontend/src/api/client.js frontend/docagent-frontend/src/stores/app.js frontend/docagent-frontend/src/composables/useApiMode.js frontend/docagent-frontend/src/api/__tests__/v2-clients.spec.js
git commit -m "feat: add frontend dual-stack api mode"
```

## Verification

- [ ] Run: `cd frontend/docagent-frontend && npm run test`
- [ ] Run: `cd frontend/docagent-frontend && npm run build`
- [ ] Manually confirm:

```text
1. Documents page shows lifecycle state.
2. Search results open a document with a block-aware anchor.
3. QA renders citations for streamed answers.
4. Graph page loads normalized nodes and edges.
5. Dashboard renders runtime dependency health.
6. Switching API mode changes requests between /api/v1 and /api/v2.
```
