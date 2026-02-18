<template>
  <div class="card search-card">
    <div class="card-header">
      <el-icon><Search /></el-icon>
      <span>智能检索</span>
    </div>
    <div class="search-box">
      <el-input
        v-model="searchQuery"
        placeholder="输入关键词/句子进行语义检索..."
        size="large"
        :prefix-icon="Search"
        @keyup.enter="handleSearch"
        clearable
      />
      <el-button 
        type="primary" 
        size="large" 
        @click="handleSearch" 
        class="search-btn" 
        :loading="loading"
      >
        搜索
      </el-button>
    </div>
    <div class="stats-info" v-if="stats">
      <el-tag type="info">📊 总分片: {{ stats.total_chunks }}</el-tag>
      <el-tag 
        type="success" 
        v-for="(count, type) in stats.file_types" 
        :key="type"
      >
        {{ type }}: {{ count }}
      </el-tag>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { api } from '@/api'

// 接收父组件传入的统计数据
const props = defineProps({
  stats: {
    type: Object,
    default: () => ({})
  }
})
// 向父组件发送事件
const emit = defineEmits(['search-result', 'refresh-stats'])

// 响应式数据
const searchQuery = ref('')
const loading = ref(false)

// 搜索逻辑
const handleSearch = async () => {
  if (!searchQuery.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  
  loading.value = true
  try {
    const res = await api.searchDocuments(searchQuery.value)
    const results = res.data || res
    // 把搜索结果传给父组件
    emit('search-result', results)
    if (results.length === 0) {
      ElMessage.info('未找到相关文档')
    }
  } catch (error) {
    console.error('搜索失败：', error)
  } finally {
    loading.value = false
  }
}

// 清空搜索时，通知父组件关闭结果面板
watch(searchQuery, (newVal) => {
  if (!newVal.trim()) {
    emit('search-result', [])
  }
})
</script>

<style scoped lang="scss">
.search-card {
  .search-box {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    
    .el-input {
      flex: 1;
    }
    
    .search-btn {
      min-width: 100px;
    }
  }
  
  .stats-info {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
}
</style>