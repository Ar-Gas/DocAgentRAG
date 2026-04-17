<template>
  <section class="page-stack search-page">
    <SearchToolbar
      v-model="filters"
      :stats="stats"
      :categories="categories"
      :loading="searchLoading"
      :can-summarize="workspace.documents.length > 0"
      :can-generate-report="workspace.documents.length > 0"
      :rebuilding-topics="rebuildingTopics"
      @search="executeSearch"
      @reset="resetWorkspace"
      @summarize="openSummaryDrawer"
      @generate-report="openClassificationDrawer"
      @rebuild-topics="rebuildTopicTree"
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

      <!-- 右列：检索概览 + 语义主题树 -->
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

        <TopicTreePanel
          :tree="topicTree"
          :loading="topicLoading"
          :rebuilding="rebuildingTopics"
          :selected-document-id="selectedDocumentId"
          :show-rebuild="true"
          @select-document="selectDocument"
          @rebuild="rebuildTopicTree"
        />
      </div>
    </div>

    <!-- 汇总抽屉 -->
    <SummaryDrawer
      v-model:visible="summaryVisible"
      :summary="summary"
      :loading="summaryLoading"
      @select-document="selectDocument"
    />

    <!-- 分类报告抽屉 -->
    <ClassificationReportDrawer
      v-model:visible="classificationVisible"
      :report="classificationReport"
      :loading="classificationLoading"
    />

    <!-- 原文预览模态框 -->
    <DocumentViewerModal
      v-if="viewerDoc"
      v-model:visible="viewerVisible"
      :document-id="viewerDoc.document_id"
      :filename="viewerDoc.filename"
      :file-type="viewerDoc.file_type"
      :query="filters.query"
      :anchor-block-id="viewerDoc.best_block_id || ''"
      :file-available="viewerDoc.file_available"
    />
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'

import ClassificationReportDrawer from '@/components/ClassificationReportDrawer.vue'
import DocumentReader from '@/components/DocumentReader.vue'
import DocumentResultList from '@/components/DocumentResultList.vue'
import DocumentViewerModal from '@/components/DocumentViewerModal.vue'
import SearchToolbar from '@/components/SearchToolbar.vue'
import SummaryDrawer from '@/components/SummaryDrawer.vue'
import TopicTreePanel from '@/components/TopicTreePanel.vue'
import { api, workspaceSearchStream } from '@/api'

const createDefaultFilters = () => ({
  query: '',
  mode: 'hybrid',
  limit: 12,
  alpha: 0.5,
  use_rerank: false,
  use_query_expansion: true,
  use_llm_rerank: true,
  expansion_method: 'llm',
  file_types: [],
  filename: '',
  classification: '',
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
const categories = ref([])
const topicTree = ref({ topics: [], total_documents: 0 })
const workspace = ref(emptyWorkspace())
const selectedDocumentId = ref('')
const readerPayload = ref(null)
const summary = ref(null)
const classificationReport = ref(null)
const searchLoading = ref(false)
const isReranking = ref(false)
const readerLoading = ref(false)
const summaryLoading = ref(false)
const classificationLoading = ref(false)
const topicLoading = ref(false)
const rebuildingTopics = ref(false)
const summaryVisible = ref(false)
const classificationVisible = ref(false)

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
  limit: filters.value.limit,
  alpha: filters.value.alpha,
  use_rerank: filters.value.use_rerank,
  use_query_expansion: filters.value.use_query_expansion,
  use_llm_rerank: filters.value.use_llm_rerank,
  expansion_method: filters.value.expansion_method,
  file_types: filters.value.file_types || [],
  filename: filters.value.filename?.trim() || null,
  classification: filters.value.classification || null,
  date_from: filters.value.date_range?.[0] || null,
  date_to: filters.value.date_range?.[1] || null,
  group_by_document: true
})

const buildWorkspaceLabel = () => {
  const parts = [
    filters.value.query,
    filters.value.filename,
    filters.value.classification,
    (filters.value.file_types || []).join(' ')
  ].filter(Boolean).join(' / ')
  return parts || '当前检索结果'
}

const normalizeCategoriesResponse = (payload) => {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.data)) return payload.data
  if (Array.isArray(payload?.data?.categories)) return payload.data.categories
  if (Array.isArray(payload?.categories)) return payload.categories
  return []
}

const loadWorkspaceChrome = async () => {
  topicLoading.value = true
  try {
    const [statsRes, categoriesRes, topicRes] = await Promise.all([
      api.getStats(),
      api.getCategories(),
      api.getTopicTree()
    ])
    stats.value = statsRes.data || {}
    categories.value = normalizeCategoriesResponse(categoriesRes)
    topicTree.value = topicRes.data || { topics: [], total_documents: 0 }
  } finally {
    topicLoading.value = false
  }
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

const _applyWorkspaceResult = async (data) => {
  workspace.value = data?.data || data || emptyWorkspace()
  // 不再自动打开第一个文档——让用户主动展开
  selectedDocumentId.value = ''
  readerPayload.value = null
}

const executeSearch = async () => {
  if (_cancelStream) { _cancelStream(); _cancelStream = null }
  searchLoading.value = true
  isReranking.value = false
  summary.value = null
  classificationReport.value = null

  const req = buildSearchRequest()

  if (req.mode === 'smart') {
    _cancelStream = workspaceSearchStream(req, {
      async onResults(data) {
        searchLoading.value = false
        isReranking.value = true
        await _applyWorkspaceResult(data)
      },
      async onReranked(data) {
        isReranking.value = false
        await _applyWorkspaceResult(data)
      },
      onDone() {
        searchLoading.value = false
        isReranking.value = false
      },
      onError(err) {
        searchLoading.value = false
        isReranking.value = false
        console.error('Smart search SSE error:', err)
      },
    })
    return
  }

  try {
    const response = await api.workspaceSearch(req)
    await _applyWorkspaceResult(response)
  } finally {
    searchLoading.value = false
  }
}

const openSummaryDrawer = async () => {
  if (!workspace.value.documents.length) return
  summaryVisible.value = true
  summaryLoading.value = true
  try {
    const response = await api.summarizeResults(buildWorkspaceLabel(), workspace.value.documents.slice(0, 12))
    summary.value = response.data || null
  } finally {
    summaryLoading.value = false
  }
}

const openClassificationDrawer = async () => {
  if (!workspace.value.documents.length) return
  classificationVisible.value = true
  classificationLoading.value = true
  try {
    const response = await api.generateClassificationTable(buildWorkspaceLabel(), workspace.value.documents.slice(0, 20), false)
    classificationReport.value = response.data || null
  } finally {
    classificationLoading.value = false
  }
}

const rebuildTopicTree = async () => {
  rebuildingTopics.value = true
  try {
    const response = await api.buildTopicTree(true)
    topicTree.value = response.data || { topics: [], total_documents: 0 }
  } finally {
    rebuildingTopics.value = false
  }
}

const resetWorkspace = () => {
  filters.value = createDefaultFilters()
  workspace.value = emptyWorkspace()
  selectedDocumentId.value = ''
  readerPayload.value = null
  summary.value = null
  classificationReport.value = null
  summaryVisible.value = false
  classificationVisible.value = false
}

onMounted(() => {
  loadWorkspaceChrome()
})
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

/* 右列：概览卡 + 主题树上下排列 */
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
