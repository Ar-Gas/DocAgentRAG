# DocAgent Rebuild Frontend Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Vue frontend from a search-and-preview shell into a document assistant with v2 API integration, query analysis visibility, document QA, graph exploration, batch summary/export actions, duplicate warnings, and admin token-usage feedback.

**Architecture:** Preserve the existing Vue 3 + Element Plus application structure, but point new flows at `/api/v2` and add focused pages/components rather than overloading the current search page. Search remains document-centric, QA becomes a dedicated workspace, graph exploration becomes a dedicated page, and document management surfaces the new LLM metadata instead of only raw classification state.

**Tech Stack:** Vue 3, Vite, Vue Router, Axios, EventSource/fetch streaming, Element Plus, Vitest, Vue Test Utils

---

## File Structure

### Frontend

- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/router/index.js`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/DashboardPage.vue`
- Create: `frontend/docagent-frontend/src/pages/QAPage.vue`
- Create: `frontend/docagent-frontend/src/pages/GraphPage.vue`
- Create: `frontend/docagent-frontend/src/components/QueryAnalysisBar.vue`
- Create: `frontend/docagent-frontend/src/components/EntityHighlight.vue`
- Create: `frontend/docagent-frontend/src/components/QASessionPanel.vue`
- Create: `frontend/docagent-frontend/src/components/GraphCanvas.vue`
- Modify: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/components/SearchToolbar.vue`
- Modify: `frontend/docagent-frontend/src/assets/styles/global.scss`
- Create: `frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js`
- Create: `frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`
- Modify: `frontend/docagent-frontend/src/api/__tests__/index.spec.js`
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`

### No Planned Changes In This Plan

- `backend/*`
  - Backend routes and services belong to the prior plans and are treated as dependencies here.

---

### Task 1: Add v2 API Client Methods And Router Entries

**Files:**
- Modify: `frontend/docagent-frontend/src/api/index.js`
- Modify: `frontend/docagent-frontend/src/router/index.js`
- Modify: `frontend/docagent-frontend/src/api/__tests__/index.spec.js`

- [ ] **Step 1: Write the failing API and router tests**

Append to `frontend/docagent-frontend/src/api/__tests__/index.spec.js`:

```javascript
import { describe, expect, it } from 'vitest'

import { api } from '@/api'

describe('api v2 helpers', () => {
  it('builds v2 qa and graph endpoints', () => {
    expect(api.getDocumentFileUrl('doc-1')).toBe('/api/v2/documents/doc-1/file')
    expect(typeof api.searchV2).toBe('function')
    expect(typeof api.streamQA).toBe('function')
    expect(typeof api.getGraph).toBe('function')
  })
})
```

Append to a new router smoke test or inline import assertion:

```javascript
import router from '@/router'

it('registers qa and graph routes', () => {
  const names = router.getRoutes().map((item) => item.name)
  expect(names).toContain('qa')
  expect(names).toContain('graph')
})
```

- [ ] **Step 2: Run the API and router tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm run test -- src/api/__tests__/index.spec.js`
Expected: FAIL because the client still points to `/api/v1` and the `qa` / `graph` routes do not exist.

- [ ] **Step 3: Implement the v2 client surface**

Update `frontend/docagent-frontend/src/api/index.js`:

```javascript
const request = axios.create({
  baseURL: '/api/v2',
  timeout: 30000,
})

export const api = {
  uploadFile: (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
      onUploadProgress: onProgress,
    })
  },
  getDocumentList: (page = 1, pageSize = 100) =>
    request.get('/documents', { params: { page, page_size: pageSize } }),
  getDocumentReader: (documentId, query = '', anchorBlockId = null) =>
    request.get(`/documents/${documentId}/reader`, { params: { query, anchor_block_id: anchorBlockId } }),
  deleteDocument: (documentId) => request.delete(`/documents/${documentId}`),
  searchV2: (payload) => request.post('/retrieval/search', payload),
  summarizeDocuments: (payload) => request.post('/retrieval/summary', payload),
  exportResults: (payload) =>
    request.post('/retrieval/export', payload, { responseType: 'blob' }),
  rerunSummary: (docIds) => request.post('/pipeline/rerun-summary', { doc_ids: docIds }),
  rerunClassification: (docIds) => request.post('/pipeline/rerun-classification', { doc_ids: docIds }),
  streamQA: (payload, handlers) => streamPost('/qa/stream', payload, handlers),
  getGraph: (docIds = []) => request.get('/topics/graph', { params: { doc_ids: docIds } }),
  submitClassificationFeedback: (payload) => request.post('/topics/feedback', payload),
  getAdminStatus: () => request.get('/admin/status'),
  getTokenUsage: () => request.get('/admin/token-usage'),
  getDocumentFileUrl: (documentId) => `/api/v2/documents/${documentId}/file`,
}

export function streamPost(path, payload, handlers = {}) {
  const ctrl = new AbortController()

  fetch(`/api/v2${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: ctrl.signal,
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          const dataLine = frame.split('\n').find((line) => line.startsWith('data: '))
          if (dataLine) handlers.onMessage?.(dataLine.slice(6))
        }
      }
      handlers.onDone?.()
    })
    .catch((error) => {
      if (error.name !== 'AbortError') handlers.onError?.(error)
    })

  return () => ctrl.abort()
}
```

Update `frontend/docagent-frontend/src/router/index.js`:

```javascript
const routes = [
  { path: '/', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue') },
  { path: '/documents', name: 'documents', component: () => import('@/pages/DocumentsPage.vue') },
  { path: '/search', name: 'search', component: () => import('@/pages/SearchPage.vue') },
  { path: '/qa', name: 'qa', component: () => import('@/pages/QAPage.vue') },
  { path: '/graph', name: 'graph', component: () => import('@/pages/GraphPage.vue') },
]
```

- [ ] **Step 4: Re-run the API and router tests**

Run: `cd frontend/docagent-frontend && npm run test -- src/api/__tests__/index.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the API and router changes**

```bash
git add frontend/docagent-frontend/src/api/index.js \
  frontend/docagent-frontend/src/router/index.js \
  frontend/docagent-frontend/src/api/__tests__/index.spec.js
git commit -m "feat: add frontend v2 api client and routes"
```

### Task 2: Implement QAPage And GraphPage

**Files:**
- Create: `frontend/docagent-frontend/src/pages/QAPage.vue`
- Create: `frontend/docagent-frontend/src/pages/GraphPage.vue`
- Create: `frontend/docagent-frontend/src/components/QASessionPanel.vue`
- Create: `frontend/docagent-frontend/src/components/GraphCanvas.vue`
- Create: `frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js`
- Create: `frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js`

- [ ] **Step 1: Write the failing page tests**

Create `frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js`:

```javascript
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  streamQA: vi.fn((_payload, { onMessage, onDone }) => {
    onMessage?.('联邦学习通过参数隔离保护隐私。')
    onDone?.()
    return () => {}
  }),
}))

vi.mock('@/api', () => ({ api }))

describe('QAPage', () => {
  it('streams answers into the session panel', async () => {
    const QAPage = (await import('@/pages/QAPage.vue')).default
    const wrapper = mount(QAPage)

    await wrapper.find('button.ask-btn').trigger('click')
    await flushPromises()

    expect(api.streamQA).toHaveBeenCalled()
    expect(wrapper.text()).toContain('联邦学习通过参数隔离保护隐私。')
  })
})
```

Create `frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js`:

```javascript
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getGraph: vi.fn().mockResolvedValue({
    data: {
      nodes: [{ id: '联邦学习', label: '联邦学习' }],
      edges: [{ from: '联邦学习', to: '隐私保护', label: '提升', doc_id: 'doc-1' }],
    },
  }),
}))

vi.mock('@/api', () => ({ api }))

describe('GraphPage', () => {
  it('loads graph payload on mount', async () => {
    const GraphPage = (await import('@/pages/GraphPage.vue')).default
    const wrapper = mount(GraphPage, { global: { stubs: { GraphCanvas: true } } })
    await flushPromises()

    expect(api.getGraph).toHaveBeenCalled()
    expect(wrapper.text()).toContain('联邦学习')
  })
})
```

- [ ] **Step 2: Run the page tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/QAPage.spec.js src/pages/__tests__/GraphPage.spec.js`
Expected: FAIL because the pages and components do not exist yet.

- [ ] **Step 3: Implement the QA and graph pages**

Create `frontend/docagent-frontend/src/pages/QAPage.vue` with a direct assistant layout:

```vue
<template>
  <section class="qa-page">
    <header class="shell-panel hero-card">
      <h2>文档问答</h2>
      <p>针对选中文档或整个知识库发问，答案会携带引用来源。</p>
      <div class="qa-controls">
        <el-input v-model="question" placeholder="例如：这些文档对联邦学习隐私保护有什么不同观点？" />
        <el-button class="ask-btn" type="primary" :loading="loading" @click="askQuestion">开始问答</el-button>
      </div>
    </header>

    <QASessionPanel :answer="answer" :citations="citations" :loading="loading" />
  </section>
</template>

<script setup>
import { ref } from 'vue'
import QASessionPanel from '@/components/QASessionPanel.vue'
import { api } from '@/api'

const question = ref('')
const answer = ref('')
const citations = ref([])
const loading = ref(false)

const askQuestion = async () => {
  loading.value = true
  answer.value = ''
  citations.value = []
  api.streamQA(
    { query: question.value || '联邦学习如何保护隐私', doc_ids: null, session_id: `qa-${Date.now()}` },
    {
      onMessage(chunk) {
        answer.value += chunk
      },
      onCitations(next) {
        citations.value = next
      },
      onDone() {
        loading.value = false
      },
      onError() {
        loading.value = false
      },
    },
  )
}
</script>
```

Create `frontend/docagent-frontend/src/pages/GraphPage.vue`:

```vue
<template>
  <section class="graph-page">
    <header class="shell-panel hero-card">
      <h2>主题图谱</h2>
      <p>浏览实体关系网络，并反向过滤相关文档。</p>
    </header>

    <section class="graph-grid">
      <GraphCanvas :nodes="graph.nodes" :edges="graph.edges" @select-node="selectedNode = $event" />
      <aside class="shell-panel graph-side">
        <h3>当前节点</h3>
        <p>{{ selectedNode || '未选择节点' }}</p>
        <ul>
          <li v-for="edge in filteredEdges" :key="`${edge.doc_id}-${edge.label}-${edge.to}`">
            {{ edge.from }} - {{ edge.label }} - {{ edge.to }}
          </li>
        </ul>
      </aside>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import GraphCanvas from '@/components/GraphCanvas.vue'
import { api } from '@/api'

const graph = ref({ nodes: [], edges: [] })
const selectedNode = ref('')

const filteredEdges = computed(() =>
  selectedNode.value
    ? graph.value.edges.filter((edge) => edge.from === selectedNode.value || edge.to === selectedNode.value)
    : graph.value.edges,
)

onMounted(async () => {
  const response = await api.getGraph()
  graph.value = response.data || { nodes: [], edges: [] }
})
</script>
```

- [ ] **Step 4: Re-run the page tests**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/QAPage.spec.js src/pages/__tests__/GraphPage.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the QA and graph pages**

```bash
git add frontend/docagent-frontend/src/pages/QAPage.vue \
  frontend/docagent-frontend/src/pages/GraphPage.vue \
  frontend/docagent-frontend/src/components/QASessionPanel.vue \
  frontend/docagent-frontend/src/components/GraphCanvas.vue \
  frontend/docagent-frontend/src/pages/__tests__/QAPage.spec.js \
  frontend/docagent-frontend/src/pages/__tests__/GraphPage.spec.js
git commit -m "feat: add qa and graph frontend pages"
```

### Task 3: Upgrade SearchPage, DocumentsPage, And Results Components

**Files:**
- Create: `frontend/docagent-frontend/src/components/QueryAnalysisBar.vue`
- Create: `frontend/docagent-frontend/src/components/EntityHighlight.vue`
- Modify: `frontend/docagent-frontend/src/pages/SearchPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- Modify: `frontend/docagent-frontend/src/pages/DashboardPage.vue`
- Modify: `frontend/docagent-frontend/src/components/DocumentResultList.vue`
- Modify: `frontend/docagent-frontend/src/components/FileList.vue`
- Modify: `frontend/docagent-frontend/src/components/SearchToolbar.vue`
- Modify: `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`

- [ ] **Step 1: Write the failing search/documents tests**

Extend `frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js`:

```javascript
// Add to the hoisted apiMocks object:
searchV2: vi.fn(),

// Replace the old workspace-search default in beforeEach():
apiMocks.searchV2.mockResolvedValue({
  data: {
    query_analysis: null,
    results: [],
    documents: [],
    total_results: 0,
    total_documents: 0,
    applied_filters: {},
  },
})

it('renders query analysis and routes qa actions through v2 payloads', async () => {
  apiMocks.searchV2.mockResolvedValue({
    data: {
      query_analysis: {
        intent: '比较分析',
        expanded_queries: ['联邦学习 隐私保护'],
        entity_filters: ['联邦学习'],
      },
      results: [
        {
          doc_id: 'doc-1',
          filename: 'paper.pdf',
          evidence_blocks: [{ block_id: 'doc-1:block-v2:0', snippet: '联邦学习用于隐私保护', entities: ['联邦学习'] }],
        },
      ],
    },
  })

  const wrapper = await mountSearchPage()
  wrapper.vm.filters.mode = 'smart'
  await wrapper.find('.go').trigger('click')
  await flushPromises()

  expect(apiMocks.searchV2).toHaveBeenCalled()
  expect(wrapper.text()).toContain('比较分析')
  expect(wrapper.text()).toContain('联邦学习')
})
```

Extend `frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js`:

```javascript
it('shows qa action and entity highlights for evidence blocks', async () => {
  const DocumentResultList = (await import('@/components/DocumentResultList.vue')).default
  const wrapper = mount(DocumentResultList, {
    props: {
      documents: [
        {
          document_id: 'doc-1',
          filename: 'paper.pdf',
          evidence_blocks: [
            {
              block_id: 'doc-1:block-v2:0',
              block_index: 0,
              snippet: '联邦学习用于隐私保护',
              entities: ['联邦学习'],
            },
          ],
        },
      ],
      query: '联邦学习',
    },
  })

  expect(wrapper.text()).toContain('加入问答')
  expect(wrapper.text()).toContain('联邦学习')
})
```

- [ ] **Step 2: Run the updated search/result tests and verify they fail**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/SearchPage.spec.js src/components/__tests__/DocumentResultList.spec.js`
Expected: FAIL because the v2 search call, query analysis bar, QA action, and entity highlighting are not implemented yet.

- [ ] **Step 3: Implement the upgraded document-centric UI**

Create `frontend/docagent-frontend/src/components/QueryAnalysisBar.vue`:

```vue
<template>
  <section class="query-analysis-bar shell-panel" v-if="analysis">
    <p class="section-label">Query Analysis</p>
    <div class="chips">
      <el-tag type="warning">{{ analysis.intent }}</el-tag>
      <el-tag v-for="item in analysis.expanded_queries" :key="item" type="info">{{ item }}</el-tag>
      <el-tag v-for="entity in analysis.entity_filters" :key="entity" type="success">{{ entity }}</el-tag>
    </div>
  </section>
</template>

<script setup>
defineProps({
  analysis: { type: Object, default: null },
})
</script>
```

Update `frontend/docagent-frontend/src/pages/SearchPage.vue` so `executeSearch()` calls `api.searchV2(req)`, stores `queryAnalysis`, and renders:

```vue
<QueryAnalysisBar :analysis="queryAnalysis" />
<DocumentResultList
  :loading="searchLoading"
  :documents="workspace.documents"
  :query="filters.query"
  :selected-document-id="selectedDocumentId"
  @add-to-qa="selectedForQA.push($event)"
  @select-document="selectDocument"
  @open-viewer="openViewer"
/>
```

Update `frontend/docagent-frontend/src/components/DocumentResultList.vue` to add a QA action button and entity chips:

```vue
<div class="entity-row" v-if="(block.entities || []).length">
  <el-tag v-for="entity in block.entities" :key="`${block.block_id}-${entity}`" size="small" type="success">
    {{ entity }}
  </el-tag>
</div>
<button type="button" class="action-btn" @click.stop="emit('add-to-qa', document.document_id)">
  加入问答
</button>
```

Update `frontend/docagent-frontend/src/pages/DocumentsPage.vue` and `FileList.vue` to render `llm_summary`, `llm_detailed_summary`, `duplicate_of`, and batch-action buttons for summarize/reclassify/export.

Update `frontend/docagent-frontend/src/pages/DashboardPage.vue` to display `api.getTokenUsage()` results in a compact admin stats card for demo use.

- [ ] **Step 4: Re-run the updated search/result tests**

Run: `cd frontend/docagent-frontend && npm run test -- src/pages/__tests__/SearchPage.spec.js src/components/__tests__/DocumentResultList.spec.js`
Expected: PASS.

- [ ] **Step 5: Commit the search/documents/dashboard upgrades**

```bash
git add frontend/docagent-frontend/src/components/QueryAnalysisBar.vue \
  frontend/docagent-frontend/src/components/EntityHighlight.vue \
  frontend/docagent-frontend/src/pages/SearchPage.vue \
  frontend/docagent-frontend/src/pages/DocumentsPage.vue \
  frontend/docagent-frontend/src/pages/DashboardPage.vue \
  frontend/docagent-frontend/src/components/DocumentResultList.vue \
  frontend/docagent-frontend/src/components/FileList.vue \
  frontend/docagent-frontend/src/components/SearchToolbar.vue \
  frontend/docagent-frontend/src/pages/__tests__/SearchPage.spec.js \
  frontend/docagent-frontend/src/components/__tests__/DocumentResultList.spec.js
git commit -m "feat: upgrade search and document management experience"
```

### Task 4: Verify The Frontend Experience End To End

**Files:**
- Modify: `frontend/docagent-frontend/src/assets/styles/global.scss`
- Verify only; no new files

- [ ] **Step 1: Add final shared styling for the new pages and components**

Update `frontend/docagent-frontend/src/assets/styles/global.scss` with shared layout tokens used by the new pages:

```scss
.hero-card {
  display: grid;
  gap: 12px;
}

.qa-page,
.graph-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.graph-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  gap: 20px;
}

@media (max-width: 960px) {
  .graph-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 2: Run the focused frontend test suite**

Run:

```bash
cd frontend/docagent-frontend && npm run test -- \
  src/api/__tests__/index.spec.js \
  src/pages/__tests__/SearchPage.spec.js \
  src/pages/__tests__/QAPage.spec.js \
  src/pages/__tests__/GraphPage.spec.js \
  src/components/__tests__/DocumentResultList.spec.js
```

Expected: PASS for all targeted frontend tests.

- [ ] **Step 3: Build the frontend bundle**

Run: `cd frontend/docagent-frontend && npm run build`
Expected: PASS with no unresolved imports for `QAPage`, `GraphPage`, or the new v2 API helpers.

- [ ] **Step 4: Smoke-test the main user flows manually**

Run the app and verify:

```text
/search shows QueryAnalysisBar and add-to-QA action
/qa streams an answer
/graph renders nodes and edges
/documents shows llm summary + duplicate warning + batch actions
/ displays token-usage demo card
```

- [ ] **Step 5: Commit any verification-only frontend fixes**

```bash
git add frontend/docagent-frontend
git commit -m "test: verify rebuilt frontend experience"
```
