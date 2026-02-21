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
          @search-query="handleSearchQuery"
          @refresh-stats="loadStats"
        />
      </div>

      <!-- 分类标签页 -->
      <el-tabs v-model="activeTab" class="classification-tabs">
        <el-tab-pane label="旧版分类" name="old">
          <ClassificationPanel 
            :document-list="documentList"
            @classify-all-success="handleOperateSuccess"
          />
        </el-tab-pane>
        <el-tab-pane label="多级分类" name="new">
          <MultiLevelClassification />
        </el-tab-pane>
      </el-tabs>

      <!-- 文档列表 -->
      <FileList 
        :document-list="documentList"
        :loading="loading"
        @refresh="loadDocuments"
        @operate-success="handleOperateSuccess"
      />
    </div>

    <!-- 检索结果弹窗 -->
    <SearchResultDialog
      v-model="showSearchDialog"
      :query="searchQuery"
      :initial-results="searchResults"
      @search-updated="handleSearchUpdated"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
// 导入所有组件
import FileUpload from '@/components/FileUpload.vue'
import SearchBox from '@/components/SearchBox.vue'
import FileList from '@/components/FileList.vue'
import ClassificationPanel from '@/components/ClassificationPanel.vue'
import MultiLevelClassification from '@/components/MultiLevelClassification.vue'
import SearchResultDialog from '@/components/SearchResultDialog.vue'
// 导入API
import { api } from '@/api'

const activeTab = ref('new')

// 响应式数据
const documentList = ref([])
const searchResults = ref([])
const searchQuery = ref('')
const showSearchDialog = ref(false)
const stats = ref(null)
const loading = ref(false)

// 加载文档列表
const loadDocuments = async () => {
  loading.value = true
  try {
    const res = await api.getDocumentList()
    documentList.value = res.data?.items || []
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

// 搜索结果回调 - 打开弹窗
const handleSearchResult = (results) => {
  searchResults.value = results
  if (results.length > 0) {
    showSearchDialog.value = true
  }
}

// 搜索查询回调
const handleSearchQuery = (query) => {
  searchQuery.value = query
}

// 搜索更新回调
const handleSearchUpdated = (results) => {
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

// 响应式适配
@media (max-width: 1024px) {
  .top-section {
    grid-template-columns: 1fr;
  }
}
</style>