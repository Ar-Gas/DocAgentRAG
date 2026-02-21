import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建axios实例
const request = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// 请求拦截器
request.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    ElMessage.error(error.response?.data?.detail || '请求失败')
    return Promise.reject(error)
  }
)

// API接口
export const api = {
  // 文档管理
  uploadFile: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  getDocumentList: (page = 1, pageSize = 10) => {
    return request.get('/documents/', { params: { page, page_size: pageSize } })
  },
  deleteDocument: (documentId) => {
    return request.delete(`/documents/${documentId}`)
  },

  // 智能分类（旧版）
  classifyDocument: (documentId) => {
    return request.post('/classification/classify', { document_id: documentId })
  },
  getCategories: () => {
    return request.get('/classification/categories')
  },
  createFolder: (documentId) => {
    return request.post(`/classification/create-folder/${documentId}`)
  },

  // 多级分类（新版）
  buildMultiLevelTree: (forceRebuild = false) => {
    return request.post('/classification/multi-level/build', { force_rebuild: forceRebuild })
  },
  getMultiLevelTree: () => {
    return request.get('/classification/multi-level/tree')
  },
  getDocumentMultiLevelInfo: (documentId) => {
    return request.get(`/classification/multi-level/document/${documentId}`)
  },

  // 语义检索
  searchDocuments: (query, limit = 10) => {
    return request.get('/retrieval/search', { params: { query, limit } })
  },
  // 混合检索（向量 + BM25）
  hybridSearch: (query, limit = 10, alpha = 0.5, useRerank = true) => {
    return request.post('/retrieval/hybrid-search', {
      query,
      limit,
      alpha,
      use_rerank: useRerank
    })
  },
  // 智能检索（查询扩展 + 多查询 + LLM重排序）
  smartSearch: (query, options = {}) => {
    return request.post('/retrieval/smart-search', {
      query,
      limit: options.limit || 10,
      use_query_expansion: options.useQueryExpansion !== false,
      use_llm_rerank: options.useLlmRerank !== false,
      expansion_method: options.expansionMethod || 'llm',
      file_types: options.fileTypes || null
    })
  },
  // 查询扩展预览
  expandQuery: (query, method = 'llm') => {
    return request.get('/retrieval/expand-query', { params: { query, method } })
  },
  // 检查LLM状态
  checkLlmStatus: () => {
    return request.get('/retrieval/llm-status')
  },
  getStats: () => {
    return request.get('/retrieval/stats')
  }
}