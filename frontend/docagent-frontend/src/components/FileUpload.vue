<template>
  <div class="upload-card shell-panel">
    <div class="upload-header">
      <span class="upload-title">上传文档</span>
      <span class="upload-hint">支持 PDF / Word / Excel / PPT / 邮件 / TXT / 图片，最大 500MB</span>
    </div>

    <el-upload
      class="upload-zone"
      drag
      :auto-upload="false"
      :on-change="handleFileChange"
      :show-file-list="false"
      :disabled="uploading"
      accept=".pdf,.docx,.doc,.xlsx,.xls,.ppt,.pptx,.eml,.msg,.txt,.jpg,.jpeg,.png,.gif,.bmp,.webp"
    >
      <div class="drop-content">
        <el-icon class="drop-icon"><UploadFilled /></el-icon>
        <p v-if="!uploading">将文件拖到此处，或<em>点击选择</em></p>
        <p v-else>上传中，请勿关闭页面…</p>
      </div>
    </el-upload>

    <!-- 上传进度 -->
    <div v-if="uploading" class="progress-block">
      <div class="progress-info">
        <span class="progress-name">{{ currentFileName }}</span>
        <span class="progress-pct">{{ uploadPercent }}%</span>
      </div>
      <el-progress :percentage="uploadPercent" :show-text="false" status="striped" striped-flow :duration="10" />
    </div>

    <!-- 最近上传结果 -->
    <div v-if="lastResult" class="last-result" :class="lastResult.success ? 'ok' : 'err'">
      <el-icon><component :is="lastResult.success ? 'CircleCheck' : 'CircleClose'" /></el-icon>
      <span>{{ lastResult.message }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { api } from '@/api'

const emit = defineEmits(['upload-success'])

const uploading = ref(false)
const uploadPercent = ref(0)
const currentFileName = ref('')
const lastResult = ref(null)

const handleFileChange = async (file) => {
  if (uploading.value) return

  uploading.value = true
  uploadPercent.value = 0
  currentFileName.value = file.name
  lastResult.value = null

  try {
    await api.uploadFile(file.raw, (evt) => {
      if (evt.total) {
        uploadPercent.value = Math.round((evt.loaded / evt.total) * 100)
      }
    })
    uploadPercent.value = 100
    lastResult.value = { success: true, message: `${file.name} 已保存，正在导入知识库` }
    emit('upload-success')
  } catch (error) {
    lastResult.value = { success: false, message: `上传失败：${error.message || '未知错误'}` }
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped lang="scss">
.upload-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.upload-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.upload-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
}

.upload-hint {
  font-size: 12px;
  color: var(--ink-muted);
}

.upload-zone {
  width: 100%;

  :deep(.el-upload-dragger) {
    width: 100%;
    height: 110px;
    border-radius: var(--radius-md);
    background: var(--bg-subtle);
    border: 2px dashed var(--line);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: border-color 0.15s, background 0.15s;

    &:hover {
      border-color: var(--blue-600);
      background: var(--blue-50);
    }
  }
}

.drop-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--ink-muted);
  font-size: 13px;

  p em {
    color: var(--blue-600);
    font-style: normal;
  }
}

.drop-icon {
  font-size: 28px;
  color: var(--ink-light);
}

.progress-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--ink-muted);
}

.progress-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 70%;
}

.last-result {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);

  &.ok {
    background: var(--green-50);
    color: var(--green-600);
    border: 1px solid #BBF7D0;
  }

  &.err {
    background: var(--red-50);
    color: var(--red-600);
    border: 1px solid #FECACA;
  }
}
</style>
