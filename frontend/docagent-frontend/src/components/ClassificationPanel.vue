<template>
  <div class="card action-card">
    <div class="action-content">
      <div class="panel-header">
        <el-icon><FolderOpened /></el-icon>
        <span>智能分类管理</span>
      </div>
      
      <div class="category-stats" v-if="categoryStats">
        <div class="stat-item" v-for="(count, category) in categoryStats" :key="category">
          <span class="category-name">{{ category }}</span>
          <el-tag type="info">{{ count }} 个文档</el-tag>
          <div class="category-actions">
            <el-button 
              type="primary" 
              size="small" 
              @click="handleCategoryReclassify(category)" 
              :loading="categoryReclassifying[category]"
            >
              批量重分类
            </el-button>
            <el-button 
              type="success" 
              size="small" 
              @click="handleCategoryRechunk(category)" 
              :loading="categoryRechunking[category]"
            >
              批量重分片
            </el-button>
          </div>
        </div>
      </div>

      <el-button 
        type="primary" 
        size="large" 
        @click="handleClassifyAll" 
        :loading="classifyingAll" 
        class="btn-primary"
      >
        一键分类所有未分类文档
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import { api } from '@/api'

// 接收父组件传入的文档列表
const props = defineProps({
  documentList: {
    type: Array,
    default: () => []
  }
})
// 向父组件发送事件
const emit = defineEmits(['classify-all-success'])

// 响应式数据
const classifyingAll = ref(false)
const categoryReclassifying = ref({})
const categoryRechunking = ref({})

// 计算分类统计
const categoryStats = computed(() => {
  const stats = {}
  props.documentList.forEach(doc => {
    const category = doc.classification_result || '未分类'
    stats[category] = (stats[category] || 0) + 1
  })
  return stats
})

// 一键全量分类
const handleClassifyAll = async () => {
  // 筛选未分类的文档
  const unclassifiedDocs = props.documentList.filter(doc => !doc.classification_result)
  
  if (unclassifiedDocs.length === 0) {
    ElMessage.info('所有文档都已分类，无需操作')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要对 ${unclassifiedDocs.length} 个未分类文档进行智能分类吗？`,
      '分类确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    classifyingAll.value = true
    // 逐个分类，避免并发请求过多导致后端压力
    for (const doc of unclassifiedDocs) {
      try {
        await api.classifyDocument(doc.id)
      } catch (error) {
        console.error(`文档 ${doc.filename} 分类失败`, error)
      }
    }
    
    ElMessage.success('一键分类完成！')
    emit('classify-all-success')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量分类失败：', error)
    }
  } finally {
    classifyingAll.value = false
  }
}

// 分类下批量重分类
const handleCategoryReclassify = async (category) => {
  if (category === '未分类') {
    ElMessage.info('未分类文档不能进行此操作，请先使用一键分类')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要对分类 "${category}" 下的所有文档进行批量重新分类吗？`,
      '批量重分类确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    categoryReclassifying.value[category] = true
    const response = await api.categoryBatchReclassify(category)
    ElMessage.success(`批量重分类完成！成功 ${response.data.success_count}/${response.data.total} 个文档`)
    emit('classify-all-success')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量重分类失败：', error)
    }
  } finally {
    categoryReclassifying.value[category] = false
  }
}

// 分类下批量重分片
const handleCategoryRechunk = async (category) => {
  if (category === '未分类') {
    ElMessage.info('未分类文档不能进行此操作')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定要对分类 "${category}" 下的所有文档进行批量重新分片吗？`,
      '批量重分片确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    categoryRechunking.value[category] = true
    const response = await api.categoryBatchRechunk(category)
    ElMessage.success(`批量重分片完成！成功 ${response.data.success_count}/${response.data.total} 个文档`)
    emit('classify-all-success')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量重分片失败：', error)
    }
  } finally {
    categoryRechunking.value[category] = false
  }
}
</script>

<style scoped lang="scss">
.action-card {
  .action-content {
    display: flex;
    align-items: center;
    gap: 30px;
    flex-wrap: wrap;
  }

  .panel-header {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 18px;
    font-weight: 600;
    color: #303133;

    .el-icon {
      font-size: 28px;
      color: #409eff;
    }
  }

  .category-stats {
    display: flex;
    gap: 15px;
    flex: 1;
    flex-wrap: wrap;

    .stat-item {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;

      .category-name {
        font-weight: 500;
        color: #606266;
      }

      .category-actions {
        display: flex;
        gap: 4px;
        margin-left: 8px;
      }
    }
  }
}
</style>