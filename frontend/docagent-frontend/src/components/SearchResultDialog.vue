<template>
  <el-dialog
    v-model="visible"
    :title="null"
    width="800px"
    :close-on-click-modal="false"
    class="search-result-dialog"
    @close="handleClose"
  >
    <template #header>
      <div class="dialog-header">
        <div class="header-left">
          <div class="search-icon">
            <el-icon><Search /></el-icon>
          </div>
          <div class="header-info">
            <h3>检索结果</h3>
            <p v-if="query">搜索: "{{ query }}"</p>
          </div>
        </div>
        <div class="header-right">
          <div class="result-count">
            <span class="count-number">{{ results.length }}</span>
            <span class="count-label">条结果</span>
          </div>
        </div>
      </div>
    </template>

    <div class="search-options" v-if="visible">
      <div class="option-item">
        <span class="option-label">检索模式:</span>
        <el-radio-group v-model="searchMode" size="small" @change="handleModeChange">
          <el-radio-button label="keyword">
            <el-tooltip content="纯关键词精确匹配，适合精确查找" placement="top">
              <span>🎯 精确检索</span>
            </el-tooltip>
          </el-radio-button>
          <el-radio-button label="smart">
            <el-tooltip content="LLM查询扩展 + 多查询检索 + LLM重排序" placement="top">
              <span>🧠 智能检索</span>
            </el-tooltip>
          </el-radio-button>
          <el-radio-button label="hybrid">混合检索</el-radio-button>
          <el-radio-button label="vector">语义检索</el-radio-button>
        </el-radio-group>
      </div>
      
      <div class="option-item" v-if="searchMode === 'smart'">
        <el-checkbox v-model="useQueryExpansion">查询扩展</el-checkbox>
        <el-checkbox v-model="useLlmRerank" style="margin-left: 12px">LLM重排序</el-checkbox>
        <el-tag v-if="!llmAvailable" type="warning" size="small" style="margin-left: 8px">
          LLM未配置
        </el-tag>
      </div>
      
      <div class="option-item" v-if="searchMode === 'hybrid'">
        <span class="option-label">语义权重:</span>
        <el-slider
          v-model="alphaValue"
          :min="0"
          :max="100"
          :format-tooltip="(val) => `${val}%`"
          size="small"
          style="width: 150px"
          @change="handleAlphaChange"
        />
        <el-checkbox v-model="useHighlight" style="margin-left: 16px">关键词高亮</el-checkbox>
      </div>

      <div class="option-item" v-if="searchMode === 'keyword'">
        <el-checkbox v-model="useHighlight">关键词高亮</el-checkbox>
      </div>
      
      <div class="option-item" v-if="searchMode === 'vector'">
        <el-checkbox v-model="useRerank">
          启用重排序
        </el-checkbox>
        <el-checkbox v-model="useHighlight" style="margin-left: 12px">关键词高亮</el-checkbox>
      </div>
    </div>

    <div class="matched-keywords" v-if="matchedKeywords.length > 0 && useHighlight">
      <div class="keywords-header">
        <el-icon><Collection /></el-icon>
        <span>匹配的关键词</span>
      </div>
      <div class="keyword-tags">
        <el-tag 
          v-for="(kw, idx) in matchedKeywords" 
          :key="idx" 
          type="danger"
          size="small"
          effect="dark"
        >
          {{ kw }}
        </el-tag>
      </div>
    </div>
    
    <div class="expanded-queries" v-if="searchMode === 'smart' && expandedQueries.length > 0">
      <div class="expansion-header">
        <el-icon><Collection /></el-icon>
        <span>扩展查询词 ({{ expandedQueries.length }}个)</span>
      </div>
      <div class="query-tags">
        <el-tag 
          v-for="(q, idx) in expandedQueries" 
          :key="idx" 
          :type="idx === 0 ? 'primary' : 'info'"
          size="small"
        >
          {{ q }}
        </el-tag>
      </div>
    </div>

    <div class="results-container" v-loading="loading">
      <transition-group name="result-list" tag="div" class="result-list">
        <div
          v-for="(item, index) in results"
          :key="item.document_id + '-' + item.chunk_index"
          class="result-card"
          :style="{ animationDelay: `${index * 0.05}s` }"
        >
          <div class="card-rank">
            <span class="rank-number">{{ index + 1 }}</span>
          </div>
          
          <div class="card-content">
            <div class="card-header">
              <div class="file-info">
                <el-icon class="file-icon" :class="getFileIconClass(item.file_type)">
                  <component :is="getFileIcon(item.file_type)" />
                </el-icon>
                <span class="filename">{{ item.filename }}</span>
                <el-tag size="small" :type="getFileTypeTag(item.file_type)">
                  {{ item.file_type || '未知' }}
                </el-tag>
              </div>
              <div class="similarity-badge" :class="getSimilarityClass(item.similarity)">
                <el-icon><TrendCharts /></el-icon>
                <span>{{ (item.similarity * 100).toFixed(1) }}%</span>
              </div>
            </div>
            
            <div class="card-body">
              <p 
                class="content-snippet" 
                :class="{ 'highlight-mode': useHighlight }"
                v-html="item.content_snippet"
              ></p>
            </div>
            
            <div class="card-footer">
              <div class="meta-info">
                <span class="meta-item">
                  <el-icon><Document /></el-icon>
                  分片 #{{ item.chunk_index + 1 }}
                </span>
                <span class="meta-item" :title="item.path">
                  <el-icon><Folder /></el-icon>
                  {{ truncatePath(item.path) }}
                </span>
              </div>
              <div class="actions">
                <el-button type="primary" size="small" text @click="viewDetail(item)">
                  <el-icon><View /></el-icon>
                  查看详情
                </el-button>
                <el-button size="small" text @click="copyContent(item)">
                  <el-icon><CopyDocument /></el-icon>
                  复制
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </transition-group>

      <div v-if="!loading && results.length === 0" class="empty-state">
        <el-icon class="empty-icon"><Search /></el-icon>
        <p>未找到相关文档</p>
        <p class="empty-hint">尝试使用不同的关键词或调整检索模式</p>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">关闭</el-button>
        <el-button type="primary" @click="handleExport">
          <el-icon><Download /></el-icon>
          导出结果
        </el-button>
      </div>
    </template>
  </el-dialog>

  <el-dialog
    v-model="detailVisible"
    :title="currentDetail?.filename"
    width="600px"
    class="detail-dialog"
  >
    <div class="detail-content" v-if="currentDetail">
      <div class="detail-meta">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="文件名">{{ currentDetail.filename }}</el-descriptions-item>
          <el-descriptions-item label="文件类型">{{ currentDetail.file_type }}</el-descriptions-item>
          <el-descriptions-item label="相似度">{{ (currentDetail.similarity * 100).toFixed(2) }}%</el-descriptions-item>
          <el-descriptions-item label="分片索引">{{ currentDetail.chunk_index + 1 }}</el-descriptions-item>
          <el-descriptions-item label="文件路径" :span="2">{{ currentDetail.path }}</el-descriptions-item>
        </el-descriptions>
      </div>
      <div class="detail-text">
        <h4>内容预览</h4>
        <pre>{{ currentDetail.content_snippet }}</pre>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Search, TrendCharts, Document, Folder, View, CopyDocument, Download,
  Document as DocIcon, Tickets, Picture, Reading, Message, Collection
} from '@element-plus/icons-vue'
import { api } from '@/api'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  query: {
    type: String,
    default: ''
  },
  initialResults: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'search-updated'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const loading = ref(false)
const results = ref([])
const searchMode = ref('hybrid')
const alphaValue = ref(50)
const useRerank = ref(true)
const useQueryExpansion = ref(true)
const useLlmRerank = ref(true)
const useHighlight = ref(true)
const llmAvailable = ref(false)
const expandedQueries = ref([])
const matchedKeywords = ref([])
const detailVisible = ref(false)
const currentDetail = ref(null)

const checkLlmStatus = async () => {
  try {
    const res = await api.checkLlmStatus()
    llmAvailable.value = res.data?.llm_available || false
  } catch {
    llmAvailable.value = false
  }
}

onMounted(() => {
  checkLlmStatus()
})

watch(() => props.initialResults, (newResults) => {
  results.value = newResults
}, { immediate: true })

watch(() => props.modelValue, (newVal) => {
  if (newVal && props.query) {
    performSearch()
  }
})

const performSearch = async () => {
  if (!props.query) return
  
  loading.value = true
  expandedQueries.value = []
  matchedKeywords.value = []
  
  try {
    let res
    if (searchMode.value === 'keyword') {
      if (useHighlight.value) {
        res = await api.searchWithHighlight(props.query, 'keyword', { limit: 10 })
        matchedKeywords.value = res.data?.keywords || []
      } else {
        res = await api.keywordSearch(props.query, 10)
      }
    } else if (searchMode.value === 'smart') {
      res = await api.smartSearch(props.query, {
        limit: 10,
        useQueryExpansion: useQueryExpansion.value,
        useLlmRerank: useLlmRerank.value,
        expansionMethod: 'llm'
      })
      expandedQueries.value = res.data?.meta?.expanded_queries || []
    } else if (searchMode.value === 'hybrid') {
      if (useHighlight.value) {
        res = await api.searchWithHighlight(props.query, 'hybrid', {
          limit: 10,
          alpha: alphaValue.value / 100,
          useRerank: useRerank.value
        })
        matchedKeywords.value = res.data?.keywords || []
      } else {
        res = await api.hybridSearch(
          props.query,
          10,
          alphaValue.value / 100,
          useRerank.value
        )
      }
    } else {
      if (useHighlight.value) {
        res = await api.searchWithHighlight(props.query, 'vector', { limit: 10 })
        matchedKeywords.value = res.data?.keywords || []
      } else {
        res = await api.searchDocuments(props.query, 10)
      }
    }
    results.value = res.data?.results || []
    emit('search-updated', results.value)
  } catch (error) {
    console.error('搜索失败:', error)
    ElMessage.error('搜索失败，请重试')
  } finally {
    loading.value = false
  }
}

const handleModeChange = () => {
  performSearch()
}

const handleAlphaChange = () => {
  performSearch()
}

const handleRerankChange = () => {
  if (searchMode.value === 'hybrid') {
    performSearch()
  }
}

const handleClose = () => {
  visible.value = false
}

const getFileIcon = (fileType) => {
  const iconMap = {
    '.pdf': Tickets,
    '.docx': DocIcon,
    '.doc': DocIcon,
    '.xlsx': Tickets,
    '.xls': Tickets,
    '.ppt': Reading,
    '.pptx': Reading,
    '.eml': Message,
    '.msg': Message,
    '.jpg': Picture,
    '.jpeg': Picture,
    '.png': Picture
  }
  return iconMap[fileType] || Document
}

const getFileIconClass = (fileType) => {
  const classMap = {
    '.pdf': 'icon-pdf',
    '.docx': 'icon-word',
    '.doc': 'icon-word',
    '.xlsx': 'icon-excel',
    '.xls': 'icon-excel',
    '.ppt': 'icon-ppt',
    '.pptx': 'icon-ppt'
  }
  return classMap[fileType] || ''
}

const getFileTypeTag = (fileType) => {
  const tagMap = {
    '.pdf': 'danger',
    '.docx': 'primary',
    '.doc': 'primary',
    '.xlsx': 'success',
    '.xls': 'success',
    '.ppt': 'warning',
    '.pptx': 'warning'
  }
  return tagMap[fileType] || 'info'
}

const getSimilarityClass = (similarity) => {
  if (similarity >= 0.8) return 'high'
  if (similarity >= 0.6) return 'medium'
  return 'low'
}

const truncatePath = (path) => {
  if (!path) return '未知路径'
  if (path.length <= 40) return path
  return '...' + path.slice(-37)
}

const viewDetail = (item) => {
  currentDetail.value = item
  detailVisible.value = true
}

const copyContent = async (item) => {
  try {
    await navigator.clipboard.writeText(item.content_snippet)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const handleExport = () => {
  const data = results.value.map((r, i) => ({
    rank: i + 1,
    filename: r.filename,
    similarity: (r.similarity * 100).toFixed(2) + '%',
    content: r.content_snippet
  }))
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `search-results-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('导出成功')
}
</script>

<style scoped lang="scss">
.search-result-dialog {
  :deep(.el-dialog__header) {
    padding: 0;
    margin: 0;
  }
  
  :deep(.el-dialog__body) {
    padding: 0 20px 20px;
  }
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px 8px 0 0;
  
  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
    
    .search-icon {
      width: 48px;
      height: 48px;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      
      .el-icon {
        font-size: 24px;
        color: white;
      }
    }
    
    .header-info {
      h3 {
        margin: 0;
        font-size: 20px;
        font-weight: 600;
        color: white;
      }
      
      p {
        margin: 4px 0 0;
        font-size: 14px;
        color: rgba(255, 255, 255, 0.8);
      }
    }
  }
  
  .header-right {
    .result-count {
      background: rgba(255, 255, 255, 0.2);
      padding: 8px 16px;
      border-radius: 20px;
      text-align: center;
      
      .count-number {
        font-size: 24px;
        font-weight: 700;
        color: white;
      }
      
      .count-label {
        font-size: 12px;
        color: rgba(255, 255, 255, 0.8);
        margin-left: 4px;
      }
    }
  }
}

.search-options {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 16px 0;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 16px;
  
  .option-item {
    display: flex;
    align-items: center;
    gap: 8px;
    
    .option-label {
      font-size: 14px;
      color: #606266;
    }
  }
}

.expanded-queries {
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  
  .expansion-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 13px;
    color: #606266;
    font-weight: 500;
    
    .el-icon {
      color: #409eff;
    }
  }
  
  .query-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
}

.matched-keywords {
  background: linear-gradient(135deg, #fef0ef 0%, #fde2e2 100%);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border: 1px solid #fdaeb1;
  
  .keywords-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 13px;
    color: #c45656;
    font-weight: 500;
    
    .el-icon {
      color: #f56c6c;
    }
  }
  
  .keyword-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
}

.results-container {
  max-height: 500px;
  overflow-y: auto;
  padding-right: 8px;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 3px;
    
    &:hover {
      background: #a1a1a1;
    }
  }
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.result-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: #fff;
  border-radius: 12px;
  border: 1px solid #ebeef5;
  transition: all 0.3s ease;
  animation: fadeInUp 0.4s ease forwards;
  opacity: 0;
  
  &:hover {
    border-color: #409eff;
    box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
    transform: translateY(-2px);
  }
  
  .card-rank {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    
    .rank-number {
      font-size: 16px;
      font-weight: 700;
      color: #409eff;
    }
  }
  
  &:nth-child(1) .card-rank {
    background: linear-gradient(135deg, #ffd700 0%, #ffb347 100%);
    .rank-number { color: white; }
  }
  
  &:nth-child(2) .card-rank {
    background: linear-gradient(135deg, #c0c0c0 0%, #a8a8a8 100%);
    .rank-number { color: white; }
  }
  
  &:nth-child(3) .card-rank {
    background: linear-gradient(135deg, #cd7f32 0%, #b8860b 100%);
    .rank-number { color: white; }
  }
  
  .card-content {
    flex: 1;
    min-width: 0;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    
    .file-info {
      display: flex;
      align-items: center;
      gap: 8px;
      
      .file-icon {
        font-size: 20px;
        color: #909399;
        
        &.icon-pdf { color: #f56c6c; }
        &.icon-word { color: #409eff; }
        &.icon-excel { color: #67c23a; }
        &.icon-ppt { color: #e6a23c; }
      }
      
      .filename {
        font-weight: 600;
        color: #303133;
        max-width: 300px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }
    
    .similarity-badge {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 4px 12px;
      border-radius: 16px;
      font-size: 14px;
      font-weight: 600;
      
      &.high {
        background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%);
        color: white;
      }
      
      &.medium {
        background: linear-gradient(135deg, #e6a23c 0%, #f0c78a 100%);
        color: white;
      }
      
      &.low {
        background: linear-gradient(135deg, #909399 0%, #b4b4b4 100%);
        color: white;
      }
    }
  }
  
  .card-body {
    .content-snippet {
      margin: 0;
      font-size: 14px;
      line-height: 1.6;
      color: #606266;
      background: #f5f7fa;
      padding: 12px;
      border-radius: 8px;
      border-left: 3px solid #409eff;
      
      &.highlight-mode {
        :deep(.highlight) {
          background-color: #f56c6c;
          color: white;
          padding: 1px 4px;
          border-radius: 3px;
          font-weight: 600;
        }
      }
    }
  }
  
  .card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #ebeef5;
    
    .meta-info {
      display: flex;
      gap: 16px;
      
      .meta-item {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: #909399;
        
        .el-icon {
          font-size: 14px;
        }
      }
    }
    
    .actions {
      display: flex;
      gap: 8px;
    }
  }
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  
  .empty-icon {
    font-size: 64px;
    color: #c0c4cc;
    margin-bottom: 16px;
  }
  
  p {
    margin: 0;
    font-size: 16px;
    color: #909399;
    
    &.empty-hint {
      font-size: 14px;
      margin-top: 8px;
    }
  }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.detail-dialog {
  .detail-content {
    .detail-meta {
      margin-bottom: 20px;
    }
    
    .detail-text {
      h4 {
        margin: 0 0 12px;
        font-size: 14px;
        color: #606266;
      }
      
      pre {
        margin: 0;
        padding: 16px;
        background: #f5f7fa;
        border-radius: 8px;
        font-size: 13px;
        line-height: 1.6;
        white-space: pre-wrap;
        word-break: break-all;
        max-height: 300px;
        overflow-y: auto;
      }
    }
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.result-list-enter-active,
.result-list-leave-active {
  transition: all 0.3s ease;
}

.result-list-enter-from,
.result-list-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}
</style>
