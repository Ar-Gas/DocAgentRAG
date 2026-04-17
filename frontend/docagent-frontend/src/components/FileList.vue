<template>
  <div class="shell-panel list-panel">
    <div class="list-header">
      <span class="list-title">文档列表</span>
      <span class="list-count">共 {{ documentList.length }} 个文档</span>
      <el-button type="primary" link size="small" @click="emit('refresh')">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <el-table :data="documentList" v-loading="loading" stripe>
      <el-table-column prop="filename" label="文件名" min-width="240">
        <template #default="{ row }">
          <div
            class="file-name-cell"
            :class="{ clickable: true, unavailable: row.file_available === false }"
            @click="emit('open-viewer', row)"
          >
            <el-icon><Document /></el-icon>
            <span>{{ row.filename }}</span>
            <el-tag v-if="row.file_available === false" size="small" type="danger">文本预览</el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="file_type" label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.file_type }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="分类" min-width="260">
        <template #default="{ row }">
          <div class="classification-cell">
            <span class="classification-text">{{ getClassificationText(row) }}</span>
            <span
              v-if="getClassificationSourceMeta(row.classification_source)"
              class="classification-source-badge"
              :class="`classification-source-badge--${getClassificationSourceMeta(row.classification_source).tone}`"
            >
              {{ getClassificationSourceMeta(row.classification_source).label }}
            </span>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="created_at_iso" label="上传时间" width="175" />

      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            link
            size="small"
            @click="handleReclassify(row)"
            :loading="row._reclassifying"
          >
            <el-icon><RefreshRight /></el-icon>
            重新分类
          </el-button>
          <el-button
            type="danger"
            link
            size="small"
            @click="handleDelete(row)"
            :loading="row._deleting"
          >
            <el-icon><Delete /></el-icon>
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Refresh, RefreshRight, Delete } from '@element-plus/icons-vue'
import { api } from '@/api'

defineProps({
  documentList: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['refresh', 'operate-success', 'open-viewer'])

const parseClassificationPath = (value) => {
  if (Array.isArray(value)) return value.filter(Boolean)
  if (typeof value !== 'string' || !value.trim()) return []

  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed.filter(Boolean) : []
  } catch (_) {
    return []
  }
}

const getClassificationText = (row) => {
  const path = parseClassificationPath(row.classification_path)
  if (path.length) return path.join(' > ')
  return row.classification_result || '未分类'
}

const getClassificationSourceMeta = (source) => {
  const dictionary = {
    llm: { label: 'AI', tone: 'ai' },
    keyword: { label: '关键词', tone: 'keyword' },
    fallback: { label: '待确认', tone: 'fallback' }
  }
  return dictionary[source] || null
}

const handleReclassify = async (row) => {
  row._reclassifying = true
  try {
    const response = await api.reclassifyDocument(row.id)
    const newClass = response.data?.new_classification || '无结果'
    ElMessage.success(`重新分类完成：${newClass}`)
    emit('operate-success')
  } catch (_) {
    // error already shown by interceptor
  } finally {
    row._reclassifying = false
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除「${row.filename}」？此操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    row._deleting = true
    await api.deleteDocument(row.id)
    ElMessage.success('已删除')
    emit('operate-success')
  } catch (error) {
    if (error !== 'cancel') {
      // error already shown by interceptor
    }
  } finally {
    row._deleting = false
  }
}
</script>

<style scoped lang="scss">
.list-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.list-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.list-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
}

.list-count {
  font-size: 12px;
  color: var(--ink-muted);
  flex: 1;
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
    color: var(--ink-strong);
  }

  &.clickable {
    cursor: pointer;
    span { color: var(--blue-600); }
    &:hover span { text-decoration: underline; }
  }

  &.unavailable {
    opacity: 0.72;
  }
}

.classification-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.classification-text {
  font-size: 13px;
  color: var(--ink-strong);
  line-height: 1.5;
}

.classification-source-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  line-height: 1;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.classification-source-badge--ai {
  background: var(--color-background-info, var(--blue-50));
  color: var(--color-text-info, var(--blue-700));
}

.classification-source-badge--keyword {
  background: var(--color-background-success, var(--green-50));
  color: var(--color-text-success, var(--green-600));
}

.classification-source-badge--fallback {
  background: var(--color-background-warning, var(--amber-50));
  color: var(--color-text-warning, var(--amber-600));
}
</style>
