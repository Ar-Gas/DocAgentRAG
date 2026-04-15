<template>
  <section class="shell-panel content-panel">
    <div class="panel-head">
      <h4>{{ mode === 'search' ? '搜索结果' : '目录内容' }}</h4>
      <span class="panel-count">
        {{ mode === 'search' ? `${searchDocuments.length} 条` : `${folders.length} 个目录 / ${documents.length} 篇文档` }}
      </span>
    </div>

    <div v-if="mode === 'directory'" class="folder-section">
      <p class="section-label">文件夹</p>
      <div v-if="folders.length" class="folder-list">
        <button
          v-for="folder in folders"
          :key="folder.node_id"
          type="button"
          class="folder-card"
          :class="{ 'is-locked': !isFolderSelectable(folder) }"
          :disabled="!isFolderSelectable(folder)"
          @click="handleOpenFolder(folder)"
        >
          <span class="folder-name">{{ folder.label }}</span>
          <span v-if="folder.locked || folder.accessible === false" class="lock-tag">锁定</span>
        </button>
      </div>
      <el-empty v-else description="当前目录没有子文件夹" />
    </div>

    <div class="document-section">
      <p class="section-label">{{ mode === 'search' ? '命中文档' : '文档' }}</p>
      <div v-if="activeDocuments.length" class="document-list">
        <article
          v-for="document in activeDocuments"
          :key="getDocumentId(document)"
          class="document-row"
          :class="{ 'is-active': getDocumentId(document) === selectedDocumentId }"
        >
          <button type="button" class="document-main" @click="handleSelectDocument(document)">
            <span class="document-title">{{ document.filename }}</span>
            <span class="document-meta">
              <span class="meta-chip">{{ toVisibilityLabel(document.visibility_scope) }}</span>
              <span v-if="document.business_category_name || document.business_category_id" class="meta-chip is-blue">
                {{ document.business_category_name || document.business_category_id }}
              </span>
              <span v-if="document.owner_department_name || document.owner_department_id" class="meta-chip is-gray">
                {{ document.owner_department_name || document.owner_department_id }}
              </span>
            </span>
          </button>

          <div class="document-actions">
            <button type="button" class="action-btn primary-btn" @click="handleSelectDocument(document)">
              阅读
            </button>
            <button
              type="button"
              class="action-btn"
              :disabled="document.file_available === false"
              @click="emit('open-viewer', document)"
            >
              预览
            </button>
          </div>
        </article>
      </div>
      <el-empty
        v-else
        :description="mode === 'search' ? '当前目录内未命中文档' : '当前目录暂无文档'"
      />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  mode: {
    type: String,
    default: 'directory',
  },
  folders: {
    type: Array,
    default: () => [],
  },
  documents: {
    type: Array,
    default: () => [],
  },
  searchDocuments: {
    type: Array,
    default: () => [],
  },
  selectedDocumentId: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['open-folder', 'select-document', 'open-viewer'])

const activeDocuments = computed(() =>
  props.mode === 'search' ? props.searchDocuments : props.documents,
)

const isFolderSelectable = (folder) => !(folder?.locked || folder?.accessible === false)

const handleOpenFolder = (folder) => {
  if (!isFolderSelectable(folder)) {
    return
  }
  emit('open-folder', {
    visibility_scope: folder.visibility_scope || null,
    department_id: folder.department_id || null,
    business_category_id: folder.business_category_id || null,
  })
}

const getDocumentId = (document) => String(document?.document_id || document?.id || '')

const handleSelectDocument = (document) => {
  emit(
    'select-document',
    getDocumentId(document),
    document?.best_block_id || null,
  )
}

const toVisibilityLabel = (visibilityScope) => {
  if (visibilityScope === 'public') {
    return '公共文档'
  }
  if (visibilityScope === 'department') {
    return '部门文档'
  }
  return '目录文档'
}
</script>

<style scoped lang="scss">
.content-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 480px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;

  h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--ink-strong);
  }
}

.panel-count {
  font-size: 12px;
  color: var(--ink-muted);
}

.section-label {
  margin-bottom: 10px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
  color: var(--ink-muted);
}

.folder-section,
.document-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.folder-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.folder-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  min-height: 72px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
  transition: 0.12s border-color, 0.12s background;

  &:hover {
    border-color: var(--blue-300);
    background: var(--blue-50);
  }

  &.is-locked {
    cursor: not-allowed;
    color: var(--ink-muted);
    background: var(--bg-panel);
    border-color: var(--line);
  }
}

.folder-name {
  font-size: 13px;
  font-weight: 600;
  text-align: left;
}

.lock-tag {
  font-size: 11px;
  color: var(--amber-700);
  background: var(--amber-50);
  border: 1px solid var(--amber-200);
  border-radius: 999px;
  padding: 1px 8px;
  flex-shrink: 0;
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.document-row {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;

  &.is-active {
    border-color: var(--blue-500);
    box-shadow: 0 0 0 2px var(--blue-100);
  }
}

.document-main {
  border: none;
  background: transparent;
  text-align: left;
  width: 100%;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.document-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-strong);
}

.document-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.meta-chip {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  color: #166534;
  border: 1px solid #BBF7D0;
  background: #F0FDF4;

  &.is-blue {
    color: #1D4ED8;
    border-color: #BFDBFE;
    background: #EFF6FF;
  }

  &.is-gray {
    color: var(--ink-muted);
    border-color: var(--line);
    background: var(--bg-subtle);
  }
}

.document-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  color: var(--ink-body);
  height: 30px;
  padding: 0 12px;
  font-size: 12px;
  cursor: pointer;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
}

.primary-btn {
  border-color: var(--blue-200);
  color: var(--blue-700);
  background: var(--blue-50);
}

@media (max-width: 900px) {
  .document-row {
    grid-template-columns: 1fr;
  }

  .document-actions {
    justify-content: flex-start;
  }
}
</style>
