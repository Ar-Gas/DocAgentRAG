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
      <el-table-column label="操作" width="420" fixed="right">
        <template #default="{ row }">
          <el-button 
            v-if="!row.classification_result"
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
            v-else
            type="warning" 
            link 
            size="small" 
            @click="handleReclassify(row)" 
            :loading="row.reclassifying"
          >
            <el-icon><RefreshRight /></el-icon>
            重新分类
          </el-button>
          <el-button 
            type="success" 
            link 
            size="small" 
            @click="handleRechunk(row)" 
            :loading="row.rechunking"
          >
            <el-icon><Refresh /></el-icon>
            重新分片
          </el-button>
          <el-button 
            v-if="row.classification_result"
            type="info" 
            link 
            size="small" 
            @click="handleClearClassification(row)" 
            :loading="row.clearingClassification"
          >
            <el-icon><Close /></el-icon>
            清除分类
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
  Document, Refresh, MagicStick, FolderAdd, Delete, RefreshRight, Close
} from '@element-plus/icons-vue'
import { api } from '@/api'

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
const emit = defineEmits(['refresh', 'operate-success'])

const handleRefresh = () => {
  emit('refresh')
}

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

const handleReclassify = async (row) => {
  row.reclassifying = true
  try {
    const response = await api.reclassifyDocument(row.id)
    ElMessage.success(`文档重新分类成功！新分类：${response.data.new_classification || '未知'}`)
    emit('operate-success')
  } catch (error) {
    console.error('重新分类失败：', error)
  } finally {
    row.reclassifying = false
  }
}

const handleClearClassification = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要清除文档 "${row.filename}" 的分类结果吗？`,
      '清除分类',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    row.clearingClassification = true
    await api.clearClassificationResult(row.id)
    ElMessage.success('分类结果已清除！')
    emit('operate-success')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清除分类失败：', error)
    }
  } finally {
    row.clearingClassification = false
  }
}

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

const handleRechunk = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要对文档 "${row.filename}" 进行重新分片吗？`,
      '重新分片确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    row.rechunking = true
    await api.rechunkDocument(row.id)
    ElMessage.success('文档重新分片成功！')
    emit('operate-success')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('重新分片失败：', error)
    }
  } finally {
    row.rechunking = false
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