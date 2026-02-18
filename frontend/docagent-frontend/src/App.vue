<template>
  <div class="app-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <h1>📄 办公文档智能分类与检索系统</h1>
      <p>支持文档上传、智能分类、向量检索、扫描版PDF OCR</p>
    </div>

    <div class="page-container">
      <!-- 顶部操作区：上传 + 搜索 -->
      <div class="top-section">
        <FileUpload @upload-success="handleUploadSuccess" />
        <SearchBox 
          :stats="stats" 
          @search-result="handleSearchResult"
          @refresh-stats="loadStats"
        />
      </div>

      <!-- 分类面板 -->
      <ClassificationPanel 
        :document-list="documentList"
        @classify-all-success="handleOperateSuccess"
      />

      <!-- 文档列表 -->
      <FileList 
        :document-list="documentList"
        :loading="loading"
        @refresh="loadDocuments"
        @operate-success="handleOperateSuccess"
      />

      <!-- 搜索结果展示区 -->
      <div class="card results-card" v-if="searchResults.length > 0">
        <div class="card-header">
          <el-icon><Search /></el-icon>
          <span>检索结果 ({{ searchResults.length }} 条)</span>
          <el-button type="primary" link @click="searchResults = []">
            关闭
          </el-button>
        </div>
        <div class="result-list">
          <div class="result-item" v-for="(item, index) in searchResults" :key="index">
            <div class="result-header">
              <span class="result-filename">{{ item.filename }}</span>
              <el-tag :type="item.similarity > 0.8 ? 'success' : item.similarity > 0.6 ? 'warning' : 'info'">
                相似度: {{ (item.similarity * 100).toFixed(0) }}%
              </el-tag>
            </div>
            <div class="result-snippet">{{ item.content_snippet }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
// 导入所有组件
import FileUpload from '@/components/FileUpload.vue'
import SearchBox from '@/components/SearchBox.vue'
import FileList from '@/components/FileList.vue'
import ClassificationPanel from '@/components/ClassificationPanel.vue'
// 导入API
import { api } from '@/api'

// 响应式数据
const documentList = ref([])
const searchResults = ref([])
const stats = ref(null)
const loading = ref(false)

// 加载文档列表
const loadDocuments = async () => {
  loading.value = true
  try {
    const res = await api.getDocumentList()
    documentList.value = res.data || res
  } catch (error) {
    console.error('加载文档列表失败', error)
  } finally {
    loading.value = false
  }
}

// 加载统计信息
const loadStats = async () => {
  try {
    const res = await api.getStats()
    stats.value = res.data || res
  } catch (error) {
    console.error('加载统计信息失败', error)
  }
}

// 上传成功后的回调
const handleUploadSuccess = () => {
  loadDocuments()
  loadStats()
}

// 搜索结果回调
const handleSearchResult = (results) => {
  searchResults.value = results
}

// 操作成功后的回调（分类、删除、移动）
const handleOperateSuccess = () => {
  loadDocuments()
  loadStats()
}

// 页面初始化加载数据
onMounted(() => {
  loadDocuments()
  loadStats()
})
</script>

<style scoped lang="scss">
.app-container {
  min-height: 100vh;
  padding-bottom: 40px;
}

.page-header {
  text-align: center;
  padding: 40px 20px 0;

  h1 {
    font-size: 36px;
    font-weight: 700;
    background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 10px;
  }

  p {
    font-size: 16px;
    color: #909399;
  }
}

.page-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 40px 20px;
}

.top-section {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  
  .el-icon {
    font-size: 24px;
    color: #409eff;
  }
}

.results-card {
  .card-header {
    justify-content: space-between;
  }
  
  .result-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  
  .result-item {
    padding: 16px;
    background-color: #f5f7fa;
    border-radius: 8px;
    border-left: 4px solid #409eff;
    transition: all 0.3s ease;
    
    &:hover {
      background-color: #ecf5ff;
      transform: translateX(4px);
    }
    
    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      
      .result-filename {
        font-weight: 600;
        color: #303133;
      }
    }
    
    .result-snippet {
      color: #606266;
      line-height: 1.6;
    }
  }
}

// 响应式适配
@media (max-width: 1024px) {
  .top-section {
    grid-template-columns: 1fr;
  }
}
</style>