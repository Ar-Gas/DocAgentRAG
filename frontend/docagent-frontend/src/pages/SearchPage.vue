<template>
  <section class="page-stack search-page">
    <SearchToolbar
      v-model="filters"
      :stats="stats"
      :departments="departments"
      :categories="categories"
      :loading="searchLoading"
      @search="executeSearch"
      @reset="resetWorkspace"
    />

    <div class="workspace-grid">
      <!-- 左列：文档列表 + 文本阅读区（上下堆叠） -->
      <div class="main-column">
        <DocumentResultList
          :loading="searchLoading"
          :documents="workspace.documents"
          :query="filters.query"
          :selected-document-id="selectedDocumentId"
          @select-document="selectDocument"
          @open-viewer="openViewer"
        />

        <!-- 文本阅读区：选中文档后才显示，位于列表下方 -->
        <DocumentReader
          v-if="readerPayload || readerLoading"
          :reader="readerPayload"
          :loading="readerLoading"
        />
      </div>

      <!-- 右列：检索概览 -->
      <div class="sidebar-stack">
        <section class="shell-panel insight-card">
          <p class="section-label">检索概览</p>
          <div class="insight-metrics">
            <article>
              <span>命中文档</span>
              <strong>{{ workspace.total_documents || 0 }}</strong>
            </article>
            <article>
              <span>证据块</span>
              <strong>{{ workspace.total_results || 0 }}</strong>
            </article>
          </div>
          <p class="insight-copy">
            {{ readerPayload?.filename
              ? `「${readerPayload.filename}」已载入，可点击段落跳转命中。`
              : '先检索文档，点击列表中的文档卡片展开证据。' }}
          </p>
        </section>
      </div>
    </div>

    <!-- 原文预览模态框 -->
    <DocumentViewerModal
      v-if="viewerDoc"
      v-model:visible="viewerVisible"
      :document-id="viewerDoc.document_id"
      :filename="viewerDoc.filename"
      :file-type="viewerDoc.file_type"
      :file-available="viewerDoc.file_available"
    />
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import DocumentReader from '@/components/DocumentReader.vue'
import DocumentResultList from '@/components/DocumentResultList.vue'
import DocumentViewerModal from '@/components/DocumentViewerModal.vue'
import SearchToolbar from '@/components/SearchToolbar.vue'
import { api, workspaceSearchStream } from '@/api'

const WORKSPACE_RETRIEVAL_VERSION = import.meta.env.VITE_WORKSPACE_RETRIEVAL_VERSION || 'legacy'

const createDefaultFilters = () => ({
  query: '',
  mode: 'hybrid',
  visibility_scope: '',
  department_id: '',
  business_category_id: '',
  limit: 12,
  alpha: 0.5,
  use_rerank: false,
  use_query_expansion: true,
  use_llm_rerank: true,
  expansion_method: 'llm',
  file_types: [],
  filename: '',
  date_range: []
})

const emptyWorkspace = () => ({
  results: [],
  documents: [],
  total_results: 0,
  total_documents: 0,
  applied_filters: {}
})

const filters = ref(createDefaultFilters())
const stats = ref({})
const departments = ref([])
const systemCategories = ref([])
const departmentCategories = ref([])
const workspace = ref(emptyWorkspace())
const selectedDocumentId = ref('')
const readerPayload = ref(null)
const searchLoading = ref(false)
const readerLoading = ref(false)

// 原文预览状态
const viewerVisible = ref(false)
const viewerDoc = ref(null)

const openViewer = (document) => {
  viewerDoc.value = document
  viewerVisible.value = true
}

const buildSearchRequest = () => ({
  query: filters.value.query?.trim() || '',
  mode: filters.value.mode,
  retrieval_version: WORKSPACE_RETRIEVAL_VERSION,
  visibility_scope: filters.value.visibility_scope || null,
  department_id: filters.value.department_id || null,
  business_category_id: filters.value.business_category_id || null,
  limit: filters.value.limit,
  alpha: filters.value.alpha,
  use_rerank: filters.value.use_rerank,
  use_query_expansion: filters.value.use_query_expansion,
  use_llm_rerank: filters.value.use_llm_rerank,
  expansion_method: filters.value.expansion_method,
  file_types: filters.value.file_types || [],
  filename: filters.value.filename?.trim() || null,
  date_from: filters.value.date_range?.[0] || null,
  date_to: filters.value.date_range?.[1] || null,
  group_by_document: true
})

const categories = computed(() => {
  const merged = [...systemCategories.value, ...departmentCategories.value]
  const seen = new Set()

  return merged.filter((category) => {
    const id = String(category?.id || '').trim()
    if (!id || seen.has(id)) {
      return false
    }
    seen.add(id)
    return true
  })
})

const loadWorkspaceChrome = async () => {
  const [statsRes, departmentsRes, systemCategoriesRes] = await Promise.all([
    api.getStats(),
    api.getDepartments(),
    api.getSystemCategories(),
  ])
  stats.value = statsRes.data || {}
  departments.value = departmentsRes.data || []
  systemCategories.value = systemCategoriesRes.data || []
}

const loadDepartmentCategories = async (departmentId) => {
  if (!departmentId) {
    departmentCategories.value = []
    return
  }

  const response = await api.getDepartmentCategories(departmentId)
  departmentCategories.value = response.data || []
}

const loadDocumentReader = async (documentId, anchorBlockId = null) => {
  if (!documentId) {
    readerPayload.value = null
    return
  }
  readerLoading.value = true
  try {
    const response = await api.getDocumentReader(documentId, filters.value.query?.trim() || '', anchorBlockId)
    readerPayload.value = response.data || null
  } finally {
    readerLoading.value = false
  }
}

const selectDocument = async (documentId, anchorBlockId = null) => {
  if (!documentId) {
    selectedDocumentId.value = ''
    readerPayload.value = null
    return
  }
  selectedDocumentId.value = documentId
  const matched = workspace.value.documents.find((item) => item.document_id === documentId)
  await loadDocumentReader(documentId, anchorBlockId || matched?.best_block_id || null)
}

let _cancelStream = null
let _workspaceRequestId = 0

const beginWorkspaceRequest = () => {
  _workspaceRequestId += 1

  if (_cancelStream) {
    _cancelStream()
    _cancelStream = null
  }

  return _workspaceRequestId
}

const isActiveWorkspaceRequest = (requestId) => requestId === _workspaceRequestId

const _applyWorkspaceResult = async (data, requestId) => {
  if (!isActiveWorkspaceRequest(requestId)) {
    return
  }

  workspace.value = data?.data || data || emptyWorkspace()
  // 不再自动打开第一个文档——让用户主动展开
  selectedDocumentId.value = ''
  readerPayload.value = null
}

const executeSearch = async () => {
  const requestId = beginWorkspaceRequest()
  searchLoading.value = true

  const req = buildSearchRequest()

  if (req.mode === 'smart' && req.retrieval_version === 'legacy') {
    _cancelStream = workspaceSearchStream(req, {
      async onResults(data) {
        if (!isActiveWorkspaceRequest(requestId)) {
          return
        }
        searchLoading.value = false
        await _applyWorkspaceResult(data, requestId)
      },
      async onReranked(data) {
        await _applyWorkspaceResult(data, requestId)
      },
      onDone() {
        if (isActiveWorkspaceRequest(requestId)) {
          searchLoading.value = false
          _cancelStream = null
        }
      },
      onError(err) {
        if (!isActiveWorkspaceRequest(requestId)) {
          return
        }
        searchLoading.value = false
        _cancelStream = null
        console.error('Smart search SSE error:', err)
      },
    })
    return
  }

  try {
    const response = await api.workspaceSearch(req)
    await _applyWorkspaceResult(response, requestId)
  } finally {
    if (isActiveWorkspaceRequest(requestId)) {
      searchLoading.value = false
    }
  }
}

const resetWorkspace = () => {
  beginWorkspaceRequest()
  searchLoading.value = false
  filters.value = createDefaultFilters()
  departmentCategories.value = []
  workspace.value = emptyWorkspace()
  selectedDocumentId.value = ''
  readerPayload.value = null
}

onMounted(() => {
  loadWorkspaceChrome()
})

onBeforeUnmount(() => {
  beginWorkspaceRequest()
})

watch(
  () => filters.value.department_id,
  async (departmentId) => {
    await loadDepartmentCategories(departmentId)
    if (
      filters.value.business_category_id &&
      !categories.value.some(
        (category) => String(category.id) === String(filters.value.business_category_id),
      )
    ) {
      filters.value.business_category_id = ''
    }
  },
)
</script>

<style scoped lang="scss">
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
  gap: 20px;
  align-items: start;
}

/* 左列：文档列表 + 阅读区上下排列 */
.main-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 右列：概览卡 */
.sidebar-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
}

.insight-card .section-label {
  margin-bottom: 12px;
}

.insight-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;

  article {
    padding: 12px 14px;
    border-radius: var(--radius-md);
    background: var(--bg-subtle);
    border: 1px solid var(--line);
  }

  span {
    display: block;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--ink-muted);
    margin-bottom: 4px;
  }

  strong {
    display: block;
    font-size: 24px;
    font-weight: 700;
    color: var(--ink-strong);
    letter-spacing: -0.02em;
  }
}

.insight-copy {
  font-size: 12px;
  color: var(--ink-muted);
  line-height: 1.7;
}

@media (max-width: 1024px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .sidebar-stack {
    position: static;
    max-height: none;
  }
}
</style>
