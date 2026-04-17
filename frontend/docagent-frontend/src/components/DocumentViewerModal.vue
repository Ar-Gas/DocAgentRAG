<template>
  <el-dialog
    :model-value="visible"
    :title="title"
    fullscreen
    class="viewer-dialog"
    destroy-on-close
    @update:model-value="emit('update:visible', $event)"
  >
    <template #header>
      <div class="viewer-header">
        <span class="viewer-title">{{ filename }}</span>
        <div class="viewer-actions">
          <el-tag size="small" type="info">{{ displayFileType }}</el-tag>
          <el-button size="small" :disabled="fileUnavailable" @click="openInNewTab">在新标签页打开</el-button>
        </div>
      </div>
    </template>

    <div v-if="fileUnavailable" class="text-fallback-viewer">
      <div class="text-fallback-banner">
        <p class="fallback-title">已切换到提取文本预览</p>
        <p class="fallback-copy">原文件不存在或路径已失效，下面展示系统保留的提取文本分片。</p>
      </div>

      <DocumentReader v-if="readerPayload || readerLoading" :reader="readerPayload" :loading="readerLoading" />

      <div v-else class="viewer-empty-state">
        <el-empty :description="readerError || '原文件不存在或路径已失效，且没有可用的提取文本。'" />
      </div>
    </div>

    <div v-else-if="isSupportedOfficePreview" class="office-viewer">
      <div v-if="officeLoading" class="office-loading-overlay">
        <el-skeleton animated :rows="8" />
      </div>

      <div v-if="officeError" class="viewer-empty-state">
        <el-empty :description="officeError" />
      </div>

      <VueOfficePdf
        v-else-if="isPdf"
        :src="fileUrl"
        class="office-preview"
        @rendered="handleOfficeRendered"
        @error="handleOfficeError"
      />

      <VueOfficeDocx
        v-else-if="isDocx"
        :src="fileUrl"
        class="office-preview"
        @rendered="handleOfficeRendered"
        @error="handleOfficeError"
      />

      <VueOfficeExcel
        v-else
        :src="fileUrl"
        class="office-preview"
        @rendered="handleOfficeRendered"
        @error="handleOfficeError"
      />
    </div>

    <div v-else class="viewer-empty-state">
      <el-empty description="暂不支持在线预览，请下载查看。" />
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import VueOfficePdf from '@vue-office/pdf'
import VueOfficeDocx from '@vue-office/docx'
import VueOfficeExcel from '@vue-office/excel'
import '@vue-office/docx/lib/index.css'
import '@vue-office/excel/lib/index.css'

import { api } from '@/api'
import DocumentReader from '@/components/DocumentReader.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  documentId: { type: String, default: '' },
  filename: { type: String, default: '' },
  fileType: { type: String, default: '' },
  query: { type: String, default: '' },
  anchorBlockId: { type: String, default: '' },
  fileAvailable: {
    default: null,
    validator: (value) => value === null || typeof value === 'boolean',
  },
})

const emit = defineEmits(['update:visible'])

const OFFICE_RENDER_TIMEOUT_MS = 15000

const officeLoading = ref(false)
const officeError = ref('')
const readerLoading = ref(false)
const readerPayload = ref(null)
const readerError = ref('')
let renderTimeoutId = null
let readerRequestToken = 0

const normalizeFileType = (fileType, filename) => {
  const rawType = (fileType || '').trim().toLowerCase()
  const candidate = rawType && !rawType.includes('/') ? rawType : ''
  const normalizedCandidate = candidate
    ? (candidate.startsWith('.') ? candidate : `.${candidate}`)
    : ''

  if (/^\.[a-z0-9]+$/.test(normalizedCandidate)) {
    return normalizedCandidate
  }

  const filenameMatch = (filename || '').trim().toLowerCase().match(/(\.[a-z0-9]+)$/)
  return filenameMatch?.[1] || ''
}

const fileUrl = computed(() => api.getDocumentFileUrl(props.documentId))
const normalizedFileType = computed(() => normalizeFileType(props.fileType, props.filename))
const fileUnavailable = computed(() => props.fileAvailable === false)
const isPdf = computed(() => normalizedFileType.value === '.pdf')
const isDocx = computed(() => normalizedFileType.value === '.docx')
const isXlsx = computed(() => normalizedFileType.value === '.xlsx')
const isSupportedOfficePreview = computed(() => isPdf.value || isDocx.value || isXlsx.value)
const displayFileType = computed(() => normalizedFileType.value || props.fileType || '未知')
const title = computed(() => props.filename || '文档预览')

const clearRenderTimeout = () => {
  if (renderTimeoutId !== null) {
    window.clearTimeout(renderTimeoutId)
    renderTimeoutId = null
  }
}

const scheduleRenderTimeout = () => {
  clearRenderTimeout()

  if (!officeLoading.value) {
    return
  }

  renderTimeoutId = window.setTimeout(() => {
    officeLoading.value = false
    officeError.value = '预览加载超时，请在新标签页打开查看。'
  }, OFFICE_RENDER_TIMEOUT_MS)
}

const resetReaderState = () => {
  readerLoading.value = false
  readerPayload.value = null
  readerError.value = ''
}

const loadExtractedTextPreview = async () => {
  if (!props.documentId) {
    readerPayload.value = null
    readerError.value = '缺少文档 ID，无法加载提取文本。'
    return
  }

  const requestToken = ++readerRequestToken
  readerLoading.value = true
  readerPayload.value = null
  readerError.value = ''

  try {
    const response = await api.getDocumentReader(
      props.documentId,
      props.query || '',
      props.anchorBlockId || null,
    )
    if (requestToken !== readerRequestToken) {
      return
    }

    const payload = response?.data || null
    if (payload?.blocks?.length) {
      readerPayload.value = payload
      return
    }

    readerPayload.value = null
    readerError.value = '原文件不存在或路径已失效，且没有可用的提取文本。'
  } catch (error) {
    if (requestToken !== readerRequestToken) {
      return
    }
    readerPayload.value = null
    readerError.value = error?.message || '加载提取文本失败。'
  } finally {
    if (requestToken === readerRequestToken) {
      readerLoading.value = false
    }
  }
}

const resetViewerState = () => {
  clearRenderTimeout()
  officeLoading.value = false
  officeError.value = ''
  resetReaderState()

  if (!props.visible) {
    return
  }

  if (fileUnavailable.value) {
    void loadExtractedTextPreview()
    return
  }

  officeLoading.value = isSupportedOfficePreview.value
  scheduleRenderTimeout()
}

const handleOfficeRendered = () => {
  clearRenderTimeout()
  officeLoading.value = false
}

const handleOfficeError = (error) => {
  clearRenderTimeout()
  officeLoading.value = false
  officeError.value = error?.message || '预览失败，请在新标签页打开查看。'
}

watch(
  () => [props.visible, props.documentId, props.fileType, props.filename, props.fileAvailable, props.query, props.anchorBlockId],
  ([visible]) => {
    if (visible) {
      resetViewerState()
      return
    }

    readerRequestToken += 1
    clearRenderTimeout()
    officeLoading.value = false
    officeError.value = ''
    resetReaderState()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  readerRequestToken += 1
  clearRenderTimeout()
})

const openInNewTab = () => {
  if (fileUnavailable.value) {
    return
  }

  window.open(fileUrl.value, '_blank', 'noopener,noreferrer')
}
</script>

<style scoped lang="scss">
.viewer-dialog :deep(.el-dialog__body) {
  padding: 0;
  height: calc(100vh - 56px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.viewer-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.viewer-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

.text-fallback-viewer {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  padding: 20px;
  overflow: hidden;
  background: var(--bg-subtle);
}

.text-fallback-banner {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line);
  background: var(--bg-panel);
}

.fallback-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
}

.fallback-copy {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-muted);
}

.office-viewer {
  position: relative;
  flex: 1;
  overflow: auto;
  background: var(--bg-subtle);
}

.office-preview {
  min-height: 100%;
}

.office-viewer :deep(.vue-office-pdf),
.office-viewer :deep(.vue-office-docx),
.office-viewer :deep(.vue-office-excel) {
  min-height: 100%;
  padding: 24px;
  background: var(--bg-subtle);
}

.office-viewer :deep(canvas) {
  display: block;
  width: min(100%, 1200px) !important;
  height: auto !important;
  margin: 0 auto 18px;
  background: #fff;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
}

.office-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
  padding: 24px;
  background: rgba(248, 250, 252, 0.92);
}

.viewer-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 24px;
  background: var(--bg-subtle);
}
</style>
