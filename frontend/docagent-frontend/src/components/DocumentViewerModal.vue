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

    <div v-if="fileUnavailable" class="viewer-empty-state">
      <el-empty description="原文件不存在或路径已失效，当前无法预览原文。" />
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

const props = defineProps({
  visible: { type: Boolean, default: false },
  documentId: { type: String, default: '' },
  filename: { type: String, default: '' },
  fileType: { type: String, default: '' },
  fileAvailable: {
    default: null,
    validator: (value) => value === null || typeof value === 'boolean',
  },
})

const emit = defineEmits(['update:visible'])

const OFFICE_RENDER_TIMEOUT_MS = 15000

const fileUrl = ref('')
const officeLoading = ref(false)
const officeError = ref('')
let renderTimeoutId = null
let previewRequestId = 0

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

const normalizedFileType = computed(() => normalizeFileType(props.fileType, props.filename))
const fileUnavailable = computed(() => props.fileAvailable === false)
const isPdf = computed(() => normalizedFileType.value === '.pdf')
const isDocx = computed(() => normalizedFileType.value === '.docx')
const isXlsx = computed(() => normalizedFileType.value === '.xlsx')
const isSupportedOfficePreview = computed(() => isPdf.value || isDocx.value || isXlsx.value)
const displayFileType = computed(() => normalizedFileType.value || props.fileType || '未知')
const title = computed(() => props.filename || '文档预览')

const revokeObjectUrl = () => {
  if (fileUrl.value) {
    URL.revokeObjectURL(fileUrl.value)
    fileUrl.value = ''
  }
}

const clearRenderTimeout = () => {
  if (renderTimeoutId !== null) {
    window.clearTimeout(renderTimeoutId)
    renderTimeoutId = null
  }
}

const nextPreviewRequestId = () => {
  previewRequestId += 1
  return previewRequestId
}

const isActivePreviewRequest = (requestId, documentId) =>
  requestId === previewRequestId && props.visible && props.documentId === documentId

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

const ensureFileUrl = async (requestId = nextPreviewRequestId()) => {
  if (fileUrl.value || !props.documentId) {
    return fileUrl.value
  }

  const requestedDocumentId = props.documentId
  const fileBlob = await api.getDocumentFileBlob(requestedDocumentId)

  if (!isActivePreviewRequest(requestId, requestedDocumentId)) {
    return ''
  }

  const nextFileUrl = URL.createObjectURL(fileBlob)

  if (!isActivePreviewRequest(requestId, requestedDocumentId)) {
    URL.revokeObjectURL(nextFileUrl)
    return ''
  }

  fileUrl.value = nextFileUrl
  return fileUrl.value
}

const resetViewerState = async () => {
  const requestId = nextPreviewRequestId()
  revokeObjectUrl()
  officeLoading.value = props.visible && !fileUnavailable.value && isSupportedOfficePreview.value
  officeError.value = ''
  scheduleRenderTimeout()

  if (!officeLoading.value) {
    return
  }

  try {
    await ensureFileUrl(requestId)
  } catch (_error) {
    if (!isActivePreviewRequest(requestId, props.documentId)) {
      return
    }

    clearRenderTimeout()
    officeLoading.value = false
    officeError.value = '预览文件加载失败，请在新标签页打开查看。'
  }
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
  () => [props.visible, props.documentId, props.fileType, props.filename, props.fileAvailable],
  async ([visible]) => {
    if (visible) {
      await resetViewerState()
      return
    }

    nextPreviewRequestId()
    clearRenderTimeout()
    revokeObjectUrl()
    officeLoading.value = false
    officeError.value = ''
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  nextPreviewRequestId()
  clearRenderTimeout()
  revokeObjectUrl()
})

const openInNewTab = async () => {
  if (fileUnavailable.value) {
    return
  }

  const previewWindow = window.open('', '_blank')
  if (previewWindow) {
    previewWindow.opener = null
  }

  try {
    const targetUrl = fileUrl.value || await ensureFileUrl(nextPreviewRequestId())
    if (targetUrl && previewWindow) {
      previewWindow.location.replace(targetUrl)
      return
    }
    if (previewWindow) {
      previewWindow.close()
    }
  } catch (_error) {
    if (previewWindow) {
      previewWindow.close()
    }
    officeError.value = '原文件加载失败，请稍后重试。'
  }
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
