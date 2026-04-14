# Vue Office Preview Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the preview modal's mixed PDF/text behavior with `vue-office` rendering for `.pdf/.docx/.xlsx`, and show an unsupported state for every other file type.

**Architecture:** Keep the existing modal and file URL contract, but collapse the preview logic into one normalized file-type switch. Supported types mount `vue-office` renderers against the original file URL, missing files short-circuit to the existing empty state, and every non-supported type skips the reader API entirely and shows a download-only message.

**Tech Stack:** Vue 3, Vite, Element Plus, `@vue-office/pdf`, `@vue-office/docx`, `@vue-office/excel`, Vitest, Vue Test Utils

---

## File Structure

### Frontend

- Modify: `frontend/docagent-frontend/package.json`
  - Add `@vue-office/docx` and `@vue-office/excel` dependencies next to the existing `@vue-office/pdf`.
- Modify: `frontend/docagent-frontend/package-lock.json`
  - Capture the exact resolved dependency tree after installing the new `vue-office` packages.
- Modify: `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`
  - Normalize `fileType`/`filename` into a single extension, mount the proper `vue-office` renderer for supported types, remove the reader/text/slides code path, and keep shared loading/error/unsupported states.
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentViewerModal.spec.js`
  - Extend coverage for `.docx`, `.xlsx`, missing-file, and unsupported-type behavior while asserting the reader API is not used by the modal.

### No Planned Changes

- `frontend/docagent-frontend/src/pages/DocumentsPage.vue`
- `frontend/docagent-frontend/src/pages/SearchPage.vue`
- `frontend/docagent-frontend/src/pages/DashboardPage.vue`

These pages already pass `file_type` and `file_available` into the modal. They should only be touched if implementation reveals a real contract mismatch.

---

### Task 1: Add The Vue Office Dependencies

**Files:**
- Modify: `frontend/docagent-frontend/package.json`
- Modify: `frontend/docagent-frontend/package-lock.json`

- [ ] **Step 1: Install the new preview packages**

Run: `cd frontend/docagent-frontend && npm install @vue-office/docx @vue-office/excel`
Expected: `package.json` gains `@vue-office/docx` and `@vue-office/excel`, and `package-lock.json` is updated.

- [ ] **Step 2: Verify the manifest changes are scoped correctly**

Check:

```json
{
  "dependencies": {
    "@vue-office/docx": "...",
    "@vue-office/excel": "...",
    "@vue-office/pdf": "^2.0.10",
    "vue-demi": "^0.14.10"
  }
}
```

Expected: the new packages appear in `dependencies`; no unrelated scripts or dependency removals are introduced.
Also verify the installed packages expose the CSS entry points used by the implementation:

- `node_modules/@vue-office/docx/lib/index.css`
- `node_modules/@vue-office/excel/lib/index.css`

If either CSS path differs in the installed version, update the implementation import path to the actual shipped stylesheet before moving on. Do not keep a broken hardcoded path and “fix it later”.

- [ ] **Step 3: Commit the dependency update**

```bash
git add frontend/docagent-frontend/package.json \
  frontend/docagent-frontend/package-lock.json
git commit -m "chore: add vue-office docx and excel preview deps"
```

### Task 2: Lock The Modal Contract With Failing Tests

**Files:**
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentViewerModal.spec.js`

- [ ] **Step 1: Extend the existing component stubs for all office renderers**

Keep the existing Element Plus stubs (`ElDialog`, `ElTag`, `ElButton`, `ElSkeleton`, `ElEmpty`) and add office-renderer stubs so the test can distinguish the supported branches:

```javascript
const STUBS = {
  VueOfficePdf: {
    name: 'VueOfficePdf',
    props: ['src'],
    template: '<div class="pdf-renderer-stub" :data-src="src">pdf renderer</div>'
  },
  VueOfficeDocx: {
    name: 'VueOfficeDocx',
    props: ['src'],
    template: '<div class="docx-renderer-stub" :data-src="src">docx renderer</div>'
  },
  VueOfficeExcel: {
    name: 'VueOfficeExcel',
    props: ['src'],
    template: '<div class="excel-renderer-stub" :data-src="src">excel renderer</div>'
  }
}
```

- [ ] **Step 2: Add failing tests for supported and unsupported routing**

Add test cases that assert:

```javascript
it('renders docx files with the docx office viewer', () => {
  const wrapper = mount(DocumentViewerModal, {
    props: {
      visible: true,
      documentId: 'doc-3',
      filename: 'report.docx',
      fileType: '.docx'
    },
    global: { stubs: STUBS }
  })

  expect(wrapper.find('.docx-renderer-stub').exists()).toBe(true)
  expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
})

it('renders xlsx files with the excel office viewer', () => {
  const wrapper = mount(DocumentViewerModal, {
    props: {
      visible: true,
      documentId: 'doc-4',
      filename: 'budget.xlsx',
      fileType: '.xlsx'
    },
    global: { stubs: STUBS }
  })

  expect(wrapper.find('.excel-renderer-stub').exists()).toBe(true)
  expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
})

it('shows unsupported state for pptx files instead of extracted text', () => {
  const wrapper = mount(DocumentViewerModal, {
    props: {
      visible: true,
      documentId: 'doc-5',
      filename: 'slides.pptx',
      fileType: '.pptx'
    },
    global: { stubs: STUBS }
  })

  expect(wrapper.text()).toContain('暂不支持在线预览')
  expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
})

it('shows unsupported state for txt files instead of extracted text', () => {
  const wrapper = mount(DocumentViewerModal, {
    props: {
      visible: true,
      documentId: 'doc-6',
      filename: 'notes.txt',
      fileType: '.txt'
    },
    global: { stubs: STUBS }
  })

  expect(wrapper.text()).toContain('暂不支持在线预览')
  expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
})

it('shows the missing-file state even for docx files', () => {
  const wrapper = mount(DocumentViewerModal, {
    props: {
      visible: true,
      documentId: 'doc-7',
      filename: 'missing.docx',
      fileType: '.docx',
      fileAvailable: false
    },
    global: { stubs: STUBS }
  })

  expect(wrapper.text()).toContain('原文件不存在')
  expect(wrapper.find('.docx-renderer-stub').exists()).toBe(false)
  expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
})

it('normalizes extension-like fileType values before routing', () => {
  const wrapper = mount(DocumentViewerModal, {
    props: {
      visible: true,
      documentId: 'doc-8',
      filename: 'report.DOCX',
      fileType: 'DOCX'
    },
    global: { stubs: STUBS }
  })

  expect(wrapper.find('.docx-renderer-stub').exists()).toBe(true)
})
```

- [ ] **Step 3: Run the targeted test to verify it fails**

Run: `cd frontend/docagent-frontend && npm test -- src/components/__tests__/DocumentViewerModal.spec.js`
Expected: FAIL because the modal still sends non-PDF files through the reader/text fallback path.

### Task 3: Refactor The Preview Modal To Office-Only Rendering

**Files:**
- Modify: `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`
- Modify: `frontend/docagent-frontend/src/components/__tests__/DocumentViewerModal.spec.js`

- [ ] **Step 1: Import the new office renderers and the verified stylesheet paths**

Replace the current single-renderer import block with:

```javascript
import { computed, ref, watch } from 'vue'
import VueOfficePdf from '@vue-office/pdf'
import VueOfficeDocx from '@vue-office/docx'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'

import { api } from '@/api'
```

If Task 1 discovered different stylesheet paths, use those verified paths here instead of the example above.

- [ ] **Step 2: Replace the file-type branching and state model**

Implement a normalization helper and supported-type booleans:

```javascript
const normalizeFileType = (fileType, filename) => {
  const rawType = (fileType || '').trim().toLowerCase()
  const candidate = rawType && !rawType.includes('/') ? rawType : ''
  const typeWithDot = candidate ? (candidate.startsWith('.') ? candidate : `.${candidate}`) : ''
  if (typeWithDot) return typeWithDot

  const match = (filename || '').toLowerCase().match(/(\.[^.]+)$/)
  return match?.[1] || ''
}

const normalizedFileType = computed(() => normalizeFileType(props.fileType, props.filename))
const fileUnavailable = computed(() => props.fileAvailable === false)
const isPdf = computed(() => normalizedFileType.value === '.pdf')
const isDocx = computed(() => normalizedFileType.value === '.docx')
const isXlsx = computed(() => normalizedFileType.value === '.xlsx')
const isSupportedOfficePreview = computed(() => isPdf.value || isDocx.value || isXlsx.value)
const isUnsupportedPreview = computed(() => !fileUnavailable.value && !isSupportedOfficePreview.value)
```

- [ ] **Step 3: Remove the reader/text/slides fallback logic and verify DOCX error support**

Delete:

```javascript
const readerLoading = ref(false)
const textContent = ref('')
const slides = ref([])

const parseSlides = (content) => { ... }

const loadContent = async () => {
  const res = await api.getDocumentReader(props.documentId, '', null)
  ...
}
```

Replace it with shared renderer state:

```javascript
const officeLoading = ref(false)
const officeError = ref('')

const resetViewerState = () => {
  officeLoading.value = props.visible && !fileUnavailable.value && isSupportedOfficePreview.value
  officeError.value = ''
}

const handleOfficeRendered = () => {
  officeLoading.value = false
}

const handleOfficeError = (error) => {
  officeLoading.value = false
  officeError.value = error?.message || '预览失败，请在新标签页打开查看。'
}
```

Before wiring template events, inspect the installed DOCX package to see whether it documents or emits an `error` event:

Run: `cd frontend/docagent-frontend && rg -n "rendered|error|emit" node_modules/@vue-office/docx -S`

Expected:

- if `error` support is visible, wire DOCX into the same shared error handler
- if `error` support is not visible, keep DOCX on the shared loading flow but only bind `@rendered`, leaving the header's new-tab action as the fallback escape hatch

- [ ] **Step 4: Replace the template branches**

Refactor the template so the modal has exactly three outcomes and uses explicit component tags so VTU stubs remain reliable:

```vue
<div v-if="fileUnavailable" class="viewer-empty-state">
  <el-empty description="原文件不存在或路径已失效，当前无法预览原文。" />
</div>

<div v-else-if="isSupportedOfficePreview" class="office-viewer">
  <div v-if="officeLoading" class="office-loading-overlay">
    <el-skeleton animated :rows="8" />
  </div>

  <VueOfficePdf
    v-if="isPdf && !officeError"
    :src="fileUrl"
    class="office-preview"
    @rendered="handleOfficeRendered"
    @error="handleOfficeError"
  />

  <VueOfficeDocx
    v-else-if="isDocx && !officeError"
    :src="fileUrl"
    class="office-preview"
    @rendered="handleOfficeRendered"
  />

  <VueOfficeExcel
    v-else-if="isXlsx && !officeError"
    :src="fileUrl"
    class="office-preview"
    @rendered="handleOfficeRendered"
    @error="handleOfficeError"
  />

  <div v-else class="viewer-empty-state">
    <el-empty :description="officeError" />
  </div>
</div>

<div v-else class="viewer-empty-state">
  <el-empty description="暂不支持在线预览，请下载查看。" />
</div>
```

If Step 3 verified that `@vue-office/docx` emits `error`, add `@error="handleOfficeError"` to `<VueOfficeDocx>` as well. If not, leave DOCX on `@rendered` only.

Keep the header tag and “在新标签页打开” button, but disable the button only when `fileUnavailable === true`.

- [ ] **Step 5: Update the watcher to stop calling the reader API**

Use the modal open/close state only to reset renderer state:

```javascript
watch(
  () => [props.visible, props.documentId, props.fileType, props.filename, props.fileAvailable],
  ([visible]) => {
    if (visible) {
      resetViewerState()
      return
    }
    officeLoading.value = false
    officeError.value = ''
  },
  { immediate: true }
)
```

- [ ] **Step 6: Run the targeted modal test again**

Run: `cd frontend/docagent-frontend && npm test -- src/components/__tests__/DocumentViewerModal.spec.js`
Expected: PASS for PDF, DOCX, XLSX, missing-file, and unsupported-format coverage, including the `.txt` regression case.

- [ ] **Step 7: Commit the modal refactor**

```bash
git add frontend/docagent-frontend/src/components/DocumentViewerModal.vue \
  frontend/docagent-frontend/src/components/__tests__/DocumentViewerModal.spec.js
git commit -m "feat: unify document preview with vue-office"
```

### Task 4: Run Full Frontend Verification

**Files:**
- Verify only: `frontend/docagent-frontend/src/components/DocumentViewerModal.vue`
- Verify only: `frontend/docagent-frontend/src/components/__tests__/DocumentViewerModal.spec.js`

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd frontend/docagent-frontend && npm test`
Expected: PASS for the full Vitest suite, including the updated modal tests.

- [ ] **Step 2: Run the production build**

Run: `cd frontend/docagent-frontend && npm run build`
Expected: PASS with a generated bundle. Existing Vite chunk-size warnings are acceptable if no new build failure is introduced.

- [ ] **Step 3: Manually smoke-test the modal in the running app**

Check these cases in the browser:

1. open a `.pdf` document and confirm the canvas-based office preview renders
2. open a `.docx` document and confirm the office preview renders instead of extracted text
3. open a `.xlsx` document and confirm the office preview renders instead of extracted text
4. open a `.pptx` or `.txt` document and confirm the unsupported message appears
5. open a missing file and confirm the missing-file message appears and the new-tab button is disabled

- [ ] **Step 4: If manual smoke testing requires a small fix, make it and rerun Steps 1-3 before the final implementation handoff**

No commit is needed here unless the smoke test exposes a real code change.
