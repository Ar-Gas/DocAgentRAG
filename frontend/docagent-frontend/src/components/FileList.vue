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
            :class="{ clickable: row.file_available !== false, unavailable: row.file_available === false }"
            @click="row.file_available !== false && emit('open-viewer', row)"
          >
            <el-icon><Document /></el-icon>
            <span>{{ row.filename }}</span>
            <el-tag v-if="row.file_available === false" size="small" type="danger">原件缺失</el-tag>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="file_type" label="类型" width="90">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.file_type }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="可见范围 / 归属部门" min-width="200">
        <template #default="{ row }">
          <div class="governance-cell">
            <el-tag size="small" :type="row.visibility_scope === 'public' ? 'success' : 'info'">
              {{ row.visibility_scope === 'public' ? '公共文档' : '部门文档' }}
            </el-tag>
            <span>{{ row.owner_department_name || row.owner_department_id || '未归属' }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="业务分类" min-width="180">
        <template #default="{ row }">
          <span>{{ row.business_category_name || row.business_category_id || '待整理' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="密级 / 状态" min-width="160">
        <template #default="{ row }">
          <div class="governance-cell">
            <span>{{ toConfidentialityLabel(row.confidentiality_level) }}</span>
            <span>{{ toStatusLabel(row.document_status) }}</span>
          </div>
        </template>
      </el-table-column>

      <el-table-column prop="created_at_iso" label="上传时间" width="175" />

      <el-table-column label="操作" width="96" fixed="right">
        <template #default="{ row }">
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
import { Document, Refresh, Delete } from '@element-plus/icons-vue'
import { api } from '@/api'

defineProps({
  documentList: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['refresh', 'operate-success', 'open-viewer'])

const toConfidentialityLabel = (level) => {
  const dictionary = {
    internal: '内部',
    confidential: '机密',
    restricted: '严格机密',
  }
  return dictionary[level] || '内部'
}

const toStatusLabel = (status) => {
  const dictionary = {
    draft: '草稿',
    published: '已发布',
    archived: '已归档',
  }
  return dictionary[status] || '草稿'
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
    cursor: not-allowed;
    opacity: 0.72;
  }
}

.governance-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--ink-muted);
}
</style>
