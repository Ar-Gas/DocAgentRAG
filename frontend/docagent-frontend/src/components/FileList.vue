<template>
  <div class="card list-card">
    <div class="card-header">
      <el-icon><Document /></el-icon>
      <span>文档列表</span>
      <el-button type="primary" link @click="handleRefresh">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>
    <el-table 
      :data="documentList" 
      style="width: 100%" 
      v-loading="loading"
      stripe
    >
      <el-table-column prop="filename" label="文件名" min-width="220">
        <template #default="{ row }">
          <div class="file-name">
            <el-icon><Document /></el-icon>
            {{ row.filename }}
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="file_type" label="文件类型" width="100">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.file_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="classification_result" label="分类结果" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.classification_result" type="success" size="small">
            {{ row.classification_result }}
          </el-tag>
          <el-tag v-else type="info" size="small">未分类</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at_iso" label="上传时间" width="180" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button 
            type="primary" 
            link 
            size="small" 
            @click="handleClassify(row)" 
            :loading="row.classifying"
          >
            <el-icon><MagicStick /></el-icon>
            分类
          </el-button>
          <el-button 
            type="success" 
            link 
            size="small" 
            @click="handleCreateFolder(row)" 
            :loading="row.creatingFolder" 
            v-if="row.classification_result"
          >
            <el-icon><FolderAdd /></el-icon>
            移动
          </el-button>
          <el-button 
            type="danger" 
            link 
            size="small" 
            @click="handleDelete(row)" 
            :loading="row.deleting"
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
import {
  Document, Refresh, MagicStick, FolderAdd, Delete
} from '@element-plus/icons-vue'
import { api } from '@/api'

// 接收父组件传入的数据
const props = defineProps({
  documentList: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})
// 向父组件发送事件
const emit = defineEmits(['refresh', 'operate-success'])

// 刷新列表
const handleRefresh = () => {
  emit('refresh')
}

// 单个文档分类
const handleClassify = async (row) => {
  row.classifying = true
  try {
    await api.classifyDocument(row.id)
    ElMessage.success('文档分类成功！')
    emit('operate-success')
  } catch (error) {
    console.error('分类失败：', error)
  } finally {
    row.classifying = false
  }
}

// 创建分类目录并移动文件
const handleCreateFolder = async (row) => {
  row.creatingFolder = true
  try {
    await api.createFolder(row.id)
    ElMessage.success('文件已移动到对应分类目录！')
    emit('operate-success')
  } catch (error) {
    console.error('移动失败：', error)
  } finally {
    row.creatingFolder = false
  }
}

// 删除文档
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${row.filename}" 吗？删除后无法恢复！`,
      '删除警告',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    row.deleting = true
    await api.deleteDocument(row.id)
    ElMessage.success('文档删除成功！')
    emit('operate-success')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败：', error)
    }
  } finally {
    row.deleting = false
  }
}
</script>

<style scoped lang="scss">
.list-card {
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  
  .file-name {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}
</style>