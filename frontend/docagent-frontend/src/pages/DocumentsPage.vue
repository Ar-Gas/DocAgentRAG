<template>
  <section class="documents-page">
    <div class="page-header shell-panel">
      <div>
        <h3>文档台账</h3>
        <p>仅展示当前账号可见的治理台账，按公共文档、部门文档与业务分类追踪文档状态。</p>
      </div>
      <div class="doc-stats">
        <article>
          <span>总文档</span>
          <strong>{{ documentList.length }}</strong>
        </article>
        <article>
          <span>公共文档</span>
          <strong>{{ publicCount }}</strong>
        </article>
        <article>
          <span>部门文档</span>
          <strong>{{ departmentCount }}</strong>
        </article>
      </div>
    </div>
    <FileList
      :document-list="documentList"
      :loading="loading"
      @refresh="loadDocuments"
      @operate-success="loadDocuments"
      @open-viewer="openViewer"
    />

    <DocumentViewerModal
      v-if="viewerDoc"
      v-model:visible="viewerVisible"
      :document-id="viewerDoc.id || viewerDoc.document_id"
      :filename="viewerDoc.filename"
      :file-type="viewerDoc.file_type"
      :file-available="viewerDoc.file_available"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import FileList from '@/components/FileList.vue'
import DocumentViewerModal from '@/components/DocumentViewerModal.vue'
import { api } from '@/api'

const documentList = ref([])
const loading = ref(false)
const viewerVisible = ref(false)
const viewerDoc = ref(null)

const openViewer = (doc) => {
  viewerDoc.value = doc
  viewerVisible.value = true
}

const publicCount = computed(() =>
  documentList.value.filter((item) => item.visibility_scope === 'public').length,
)

const departmentCount = computed(() =>
  documentList.value.filter((item) => item.visibility_scope !== 'public').length,
)

const loadDocuments = async () => {
  loading.value = true
  try {
    const response = await api.getDocumentList(1, 200)
    documentList.value = response.data?.items || []
  } finally {
    loading.value = false
  }
}

onMounted(loadDocuments)
</script>

<style scoped lang="scss">
.documents-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--ink-strong);
    margin-bottom: 4px;
  }

  p {
    color: var(--ink-muted);
    font-size: 13px;
    line-height: 1.6;
  }
}

.doc-stats {
  display: flex;
  gap: 10px;

  article {
    min-width: 80px;
    padding: 10px 16px;
    border-radius: var(--radius-md);
    background: var(--bg-subtle);
    border: 1px solid var(--line);
    text-align: center;

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
      font-size: 22px;
      font-weight: 700;
      color: var(--ink-strong);
      letter-spacing: -0.02em;
    }
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
