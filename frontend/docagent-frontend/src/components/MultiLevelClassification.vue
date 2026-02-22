<template>
  <div class="multi-level-classification">
    <div class="card action-card">
      <div class="action-content">
        <div class="panel-header">
          <el-icon><FolderOpened /></el-icon>
          <span>多级分类管理</span>
        </div>
        
        <div class="tree-search">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索分类或文档..."
            clearable
            :prefix-icon="Search"
            @input="handleSearch"
          />
        </div>
        
        <div class="tree-actions">
          <el-button type="primary" @click="handleBuildTree" :loading="building">
            <el-icon><Refresh /></el-icon>
            重新构建分类树
          </el-button>
          <el-button @click="handleForceRebuild" :loading="building">
            <el-icon><DocumentAdd /></el-icon>
            强制重建
          </el-button>
        </div>
        
        <div class="tree-info" v-if="classificationTree">
          <el-tag type="info">文档总数: {{ classificationTree.total_documents }}</el-tag>
          <el-tag type="success">生成时间: {{ formatTime(classificationTree.generated_at) }}</el-tag>
          <el-tag v-if="classificationTree.updated_at" type="warning">更新时间: {{ formatTime(classificationTree.updated_at) }}</el-tag>
        </div>
      </div>
    </div>

    <div class="classification-container" v-loading="loading">
      <div v-if="!classificationTree || !classificationTree.tree || Object.keys(classificationTree.tree).length === 0" class="empty-state">
        <el-empty description="暂无分类数据，请点击上方按钮构建分类树" />
      </div>
      
      <div v-else class="content-categories">
        <div v-for="(types, contentCategory) in filteredTree" :key="contentCategory" class="content-category">
          <div class="category-header">
            <el-icon class="category-icon"><Folder /></el-icon>
            <h3 class="category-title">{{ contentCategory }}</h3>
            <el-tag type="info" size="small">{{ countDocumentsInCategory(types) }}个文档</el-tag>
          </div>
          
          <div class="file-types">
            <div v-for="(times, fileType) in types" :key="fileType" class="file-type">
              <div class="type-header">
                <el-icon class="type-icon"><Files /></el-icon>
                <span class="type-title">{{ getFileTypeName(fileType) }}</span>
                <el-tag type="success" size="small">{{ countDocumentsInType(times) }}个</el-tag>
              </div>
              
              <div class="time-groups">
                <div v-for="(docs, timeGroup) in times" :key="timeGroup" class="time-group">
                  <div class="time-header">
                    <el-icon class="time-icon"><Clock /></el-icon>
                    <span class="time-title">{{ timeGroup }}</span>
                    <el-tag type="warning" size="small">{{ docs.length }}个</el-tag>
                  </div>
                  
                  <div class="documents-list">
                    <div 
                      v-for="doc in docs" 
                      :key="doc.document_id" 
                      class="document-item"
                    >
                      <div class="doc-info" @click="handleDocClick(doc)">
                        <el-icon class="doc-icon"><Document /></el-icon>
                        <span class="doc-name">{{ doc.filename }}</span>
                        <div v-if="doc.content_keywords && doc.content_keywords.length > 0" class="keywords">
                          <el-tag 
                            v-for="(kw, idx) in doc.content_keywords.slice(0, 3)" 
                            :key="idx" 
                            size="small" 
                            type="info"
                            class="keyword-tag"
                          >
                            {{ kw }}
                          </el-tag>
                        </div>
                      </div>
                      <div class="doc-actions">
                        <el-button 
                          type="warning" 
                          link 
                          size="small" 
                          @click.stop="handleReclassify(doc)"
                          :loading="doc.reclassifying"
                          title="重新分类"
                        >
                          <el-icon><RefreshRight /></el-icon>
                        </el-button>
                        <el-button 
                          type="info" 
                          link 
                          size="small" 
                          @click.stop="handleClearClassification(doc)"
                          :loading="doc.clearingClassification"
                          title="清除分类"
                        >
                          <el-icon><Close /></el-icon>
                        </el-button>
                        <el-button 
                          type="danger" 
                          link 
                          size="small" 
                          @click.stop="handleDelete(doc)"
                          :loading="doc.deleting"
                          title="删除文档"
                        >
                          <el-icon><Delete /></el-icon>
                        </el-button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 文档详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="文档详情"
      size="40%"
    >
      <div v-if="selectedDoc" class="doc-detail">
        <div class="detail-item">
          <span class="label">文件名:</span>
          <span class="value">{{ selectedDoc.filename }}</span>
        </div>
        <div class="detail-item">
          <span class="label">内容分类:</span>
          <el-tag type="primary">{{ selectedDoc.content_category }}</el-tag>
        </div>
        <div class="detail-item">
          <span class="label">文件类型:</span>
          <el-tag type="success">{{ getFileTypeName(selectedDoc.file_type) }}</el-tag>
        </div>
        <div class="detail-item">
          <span class="label">时间分组:</span>
          <el-tag type="warning">{{ selectedDoc.time_group }}</el-tag>
        </div>
        <div v-if="selectedDoc.content_keywords" class="detail-item">
          <span class="label">内容关键词:</span>
          <div class="keywords-list">
            <el-tag v-for="(kw, idx) in selectedDoc.content_keywords" :key="idx" size="small" type="info">
              {{ kw }}
            </el-tag>
          </div>
        </div>
        <div class="detail-item">
          <span class="label">分类路径:</span>
          <span class="value">{{ selectedDoc.classification_path }}</span>
        </div>
        <div v-if="selectedDoc.created_at_iso" class="detail-item">
          <span class="label">创建时间:</span>
          <span class="value">{{ formatTime(selectedDoc.created_at_iso) }}</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FolderOpened, Refresh, DocumentAdd, Folder, Files, Clock, Document, Search, RefreshRight, Close, Delete } from '@element-plus/icons-vue'
import { api } from '@/api'

const loading = ref(false)
const building = ref(false)
const classificationTree = ref(null)
const searchKeyword = ref('')
const drawerVisible = ref(false)
const selectedDoc = ref(null)

const filteredTree = computed(() => {
  if (!classificationTree.value || !classificationTree.value.tree) {
    return {}
  }
  
  const tree = classificationTree.value.tree
  
  if (!searchKeyword.value) {
    return tree
  }
  
  const keyword = searchKeyword.value.toLowerCase()
  const filtered = {}
  
  for (const [contentCat, types] of Object.entries(tree)) {
    const filteredTypes = {}
    let categoryHasMatch = contentCat.toLowerCase().includes(keyword)
    
    for (const [fileType, times] of Object.entries(types)) {
      const filteredTimes = {}
      let typeHasMatch = getFileTypeName(fileType).toLowerCase().includes(keyword)
      
      for (const [timeGroup, docs] of Object.entries(times)) {
        const filteredDocs = docs.filter(doc => {
          const docMatch = doc.filename.toLowerCase().includes(keyword) ||
            (doc.content_keywords && doc.content_keywords.some(kw => kw.toLowerCase().includes(keyword)))
          return docMatch || timeGroup.toLowerCase().includes(keyword)
        })
        
        if (filteredDocs.length > 0) {
          filteredTimes[timeGroup] = filteredDocs
          typeHasMatch = true
        }
      }
      
      if (Object.keys(filteredTimes).length > 0) {
        filteredTypes[fileType] = filteredTimes
        categoryHasMatch = true
      }
    }
    
    if (Object.keys(filteredTypes).length > 0 || categoryHasMatch) {
      filtered[contentCat] = Object.keys(filteredTypes).length > 0 ? filteredTypes : types
    }
  }
  
  return filtered
})

function getFileTypeName(type) {
  const typeMap = {
    'pdf': 'PDF文档',
    'word': 'Word文档',
    'excel': 'Excel表格',
    'ppt': 'PPT演示',
    'eml': '邮件',
    'txt': '文本文件',
    'other': '其他'
  }
  return typeMap[type] || type
}

function countDocumentsInCategory(types) {
  let count = 0
  for (const times of Object.values(types)) {
    count += countDocumentsInType(times)
  }
  return count
}

function countDocumentsInType(times) {
  let count = 0
  for (const docs of Object.values(times)) {
    count += docs.length
  }
  return count
}

function formatTime(isoString) {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN')
}

function handleSearch() {
}

function handleDocClick(doc) {
  selectedDoc.value = doc
  drawerVisible.value = true
}

async function handleReclassify(doc) {
  doc.reclassifying = true
  try {
    const response = await api.reclassifyDocument(doc.document_id)
    ElMessage.success(`文档重新分类成功！新分类：${response.data.new_classification || '未知'}`)
    await loadTree()
  } catch (error) {
    console.error('重新分类失败：', error)
    ElMessage.error('重新分类失败')
  } finally {
    doc.reclassifying = false
  }
}

async function handleClearClassification(doc) {
  try {
    await ElMessageBox.confirm(
      `确定要清除文档 "${doc.filename}" 的分类结果吗？`,
      '清除分类',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    doc.clearingClassification = true
    await api.clearClassificationResult(doc.document_id)
    ElMessage.success('分类结果已清除！')
    await loadTree()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清除分类失败：', error)
      ElMessage.error('清除分类失败')
    }
  } finally {
    doc.clearingClassification = false
  }
}

async function handleDelete(doc) {
  console.log('handleDelete called with doc:', doc)
  console.log('doc.document_id:', doc.document_id, 'type:', typeof doc.document_id)
  
  if (!doc.document_id) {
    ElMessage.error('文档ID无效，无法删除')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${doc.filename}" 吗？删除后无法恢复！`,
      '删除警告',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    doc.deleting = true
    await api.deleteDocument(doc.document_id)
    ElMessage.success('文档删除成功！')
    await loadTree()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败：', error)
      ElMessage.error('删除失败')
    }
  } finally {
    doc.deleting = false
  }
}

async function loadTree() {
  loading.value = true
  try {
    const response = await api.getMultiLevelTree()
    if (response.code === 200) {
      classificationTree.value = response.data
    }
  } catch (error) {
    console.error('加载分类树失败:', error)
    ElMessage.error('加载分类树失败')
  } finally {
    loading.value = false
  }
}

async function handleBuildTree() {
  building.value = true
  try {
    const response = await api.buildMultiLevelTree(false)
    if (response.code === 200) {
      classificationTree.value = response.data
      ElMessage.success('分类树构建成功')
    }
  } catch (error) {
    console.error('构建分类树失败:', error)
    ElMessage.error('构建分类树失败')
  } finally {
    building.value = false
  }
}

async function handleForceRebuild() {
  building.value = true
  try {
    const response = await api.buildMultiLevelTree(true)
    if (response.code === 200) {
      classificationTree.value = response.data
      ElMessage.success('强制重建成功')
    }
  } catch (error) {
    console.error('强制重建分类树失败:', error)
    ElMessage.error('强制重建分类树失败')
  } finally {
    building.value = false
  }
}

onMounted(() => {
  loadTree()
})
</script>

<style scoped lang="scss">
.multi-level-classification {
  .action-card {
    margin-bottom: 20px;
    
    .action-content {
      display: flex;
      align-items: center;
      gap: 20px;
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
    
    .tree-search {
      flex: 1;
      min-width: 200px;
    }
    
    .tree-actions {
      display: flex;
      gap: 10px;
    }
    
    .tree-info {
      display: flex;
      gap: 10px;
    }
  }
  
  .classification-container {
    background: white;
    border-radius: 8px;
    padding: 20px;
    min-height: 400px;
    
    .empty-state {
      padding: 60px 0;
    }
  }
  
  .content-categories {
    display: flex;
    flex-direction: column;
    gap: 24px;
    
    .content-category {
      border: 1px solid #e4e7ed;
      border-radius: 8px;
      overflow: hidden;
      
      .category-header {
        background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%);
        padding: 16px 20px;
        display: flex;
        align-items: center;
        gap: 12px;
        border-bottom: 1px solid #e4e7ed;
        
        .category-icon {
          font-size: 24px;
          color: #409eff;
        }
        
        .category-title {
          margin: 0;
          font-size: 18px;
          font-weight: 600;
          color: #303133;
        }
      }
      
      .file-types {
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 20px;
        
        .file-type {
          background: #f5f7fa;
          border-radius: 6px;
          padding: 16px;
          
          .type-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 12px;
            
            .type-icon {
              font-size: 20px;
              color: #67c23a;
            }
            
            .type-title {
              font-size: 15px;
              font-weight: 600;
              color: #606266;
            }
          }
          
          .time-groups {
            display: flex;
            flex-direction: column;
            gap: 12px;
            
            .time-group {
              background: white;
              border-radius: 4px;
              padding: 12px;
              
              .time-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 10px;
                
                .time-icon {
                  font-size: 16px;
                  color: #e6a23c;
                }
                
                .time-title {
                  font-size: 14px;
                  font-weight: 500;
                  color: #909399;
                }
              }
              
              .documents-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                
                .document-item {
                  display: flex;
                  align-items: center;
                  justify-content: space-between;
                  padding: 8px 12px;
                  background: #f5f7fa;
                  border-radius: 4px;
                  transition: all 0.2s;
                  min-width: 280px;
                  
                  &:hover {
                    background: #ecf5ff;
                    transform: translateY(-1px);
                  }
                  
                  .doc-info {
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    flex: 1;
                    cursor: pointer;
                    overflow: hidden;
                    
                    .doc-icon {
                      font-size: 16px;
                      color: #909399;
                      flex-shrink: 0;
                    }
                    
                    .doc-name {
                      font-size: 13px;
                      color: #606266;
                      max-width: 150px;
                      overflow: hidden;
                      text-overflow: ellipsis;
                      white-space: nowrap;
                    }
                    
                    .keywords {
                      display: flex;
                      gap: 4px;
                      margin-left: 8px;
                      
                      .keyword-tag {
                        margin: 0;
                      }
                    }
                  }
                  
                  .doc-actions {
                    display: flex;
                    align-items: center;
                    gap: 2px;
                    margin-left: 8px;
                    opacity: 0;
                    transition: opacity 0.2s;
                  }
                  
                  &:hover .doc-actions {
                    opacity: 1;
                  }
                }
              }
            }
          }
        }
      }
    }
  }
  
  .doc-detail {
    .detail-item {
      margin-bottom: 20px;
      display: flex;
      gap: 10px;
      align-items: flex-start;
      
      .label {
        font-weight: 600;
        color: #606266;
        min-width: 100px;
      }
      
      .value {
        color: #303133;
        flex: 1;
      }
      
      .keywords-list {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
    }
  }
}
</style>
