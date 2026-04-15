<template>
  <section class="directory-home page-stack">
    <DirectorySearchBar
      :query="query"
      :loading="searchLoading"
      @update:query="query = $event"
      @search="runScopedSearch"
      @reset="resetSearch"
    />

    <section class="shell-panel scope-banner">
      <div>
        <p class="scope-label">当前目录</p>
        <h3>{{ workspace?.current_scope?.title || '全局目录' }}</h3>
      </div>
      <p class="scope-path">
        {{ breadcrumbText }}
      </p>
    </section>

    <div class="workspace-grid">
      <DirectoryTreePanel
        :nodes="workspace?.tree || []"
        :active-scope-key="workspace?.current_scope?.scope_key || 'root'"
        @select-scope="loadWorkspace"
      />

      <div class="main-column">
        <DirectoryContentPanel
          :mode="contentMode"
          :folders="workspace?.folders || []"
          :documents="workspace?.documents || []"
          :search-documents="searchDocuments"
          :selected-document-id="selectedDocumentId"
          @open-folder="loadWorkspace"
          @select-document="selectDocument"
          @open-viewer="openViewer"
        />

        <DocumentReader
          v-if="readerPayload || readerLoading"
          :reader="readerPayload"
          :loading="readerLoading"
        />
      </div>
    </div>

    <DocumentViewerModal
      v-if="viewerDoc"
      v-model:visible="viewerVisible"
      :document-id="viewerDoc.document_id || viewerDoc.id"
      :filename="viewerDoc.filename"
      :file-type="viewerDoc.file_type"
      :file-available="viewerDoc.file_available"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import DirectoryContentPanel from '@/components/DirectoryContentPanel.vue'
import DirectorySearchBar from '@/components/DirectorySearchBar.vue'
import DirectoryTreePanel from '@/components/DirectoryTreePanel.vue'
import DocumentReader from '@/components/DocumentReader.vue'
import DocumentViewerModal from '@/components/DocumentViewerModal.vue'
import { api } from '@/api'

const emptyWorkspace = () => ({
  current_scope: { scope_key: 'root', title: '全局目录' },
  breadcrumbs: [{ label: '全局目录' }],
  tree: [],
  folders: [],
  documents: [],
  search_scope: {
    visibility_scope: null,
    department_id: null,
    business_category_id: null,
  },
})

const workspace = ref(emptyWorkspace())
const query = ref('')
const loading = ref(false)
const searchLoading = ref(false)
const searchDocuments = ref([])
const selectedDocumentId = ref('')
const readerPayload = ref(null)
const readerLoading = ref(false)
const viewerVisible = ref(false)
const viewerDoc = ref(null)
const searchMode = ref(false)

const contentMode = computed(() => (searchMode.value ? 'search' : 'directory'))
const breadcrumbText = computed(() => (workspace.value?.breadcrumbs || []).map((item) => item.label).join(' / '))

const clearSelection = () => {
  selectedDocumentId.value = ''
  readerPayload.value = null
}

const loadWorkspace = async (params = {}) => {
  loading.value = true
  try {
    const response = await api.getDirectoryWorkspace(params)
    workspace.value = response?.data || emptyWorkspace()
    searchDocuments.value = []
    searchMode.value = false
    query.value = ''
    clearSelection()
  } finally {
    loading.value = false
  }
}

const runScopedSearch = async () => {
  const trimmedQuery = query.value.trim()
  if (!trimmedQuery || !workspace.value?.search_scope) {
    searchDocuments.value = []
    searchMode.value = false
    clearSelection()
    return
  }

  searchLoading.value = true
  try {
    const response = await api.workspaceSearch({
      query: trimmedQuery,
      mode: 'hybrid',
      limit: 20,
      group_by_document: true,
      ...workspace.value.search_scope,
    })
    searchDocuments.value = response?.data?.documents || []
    searchMode.value = true
    clearSelection()
  } finally {
    searchLoading.value = false
  }
}

const selectDocument = async (documentId, anchorBlockId = null) => {
  if (!documentId) {
    clearSelection()
    return
  }

  selectedDocumentId.value = String(documentId)
  readerLoading.value = true
  try {
    const response = await api.getDocumentReader(documentId, query.value.trim(), anchorBlockId)
    readerPayload.value = response?.data || null
  } finally {
    readerLoading.value = false
  }
}

const openViewer = (document) => {
  viewerDoc.value = document
  viewerVisible.value = true
}

const resetSearch = async () => {
  searchDocuments.value = []
  searchMode.value = false
  query.value = ''
  clearSelection()
  await loadWorkspace(workspace.value?.search_scope || {})
}

onMounted(async () => {
  await loadWorkspace({})
})
</script>

<style scoped lang="scss">
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.scope-banner {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 14px;
  flex-wrap: wrap;

  h3 {
    margin-top: 4px;
    font-size: 18px;
    font-weight: 700;
    color: var(--ink-strong);
  }
}

.scope-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-muted);
  font-weight: 600;
}

.scope-path {
  font-size: 12px;
  color: var(--ink-muted);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.main-column {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

@media (max-width: 1024px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}
</style>
