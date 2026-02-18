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
  getDocumentList: (page = 1, pageSize = 20) => {
    return request.get('/documents/', { params: { page, page_size: pageSize } })
  },
  deleteDocument: (documentId) => {
    return request.delete(`/documents/${documentId}`)
  },

  // 智能分类
  classifyDocument: (documentId) => {
    return request.post('/classification/classify', { document_id: documentId })
  },
  getCategories: () => {
    return request.get('/classification/categories')
  },
  createFolder: (documentId) => {
    return request.post(`/classification/create-folder/${documentId}`)
  },

  // 语义检索
  searchDocuments: (query, limit = 10) => {
    return request.get('/retrieval/search', { params: { query, limit } })
  },
  getStats: () => {
    return request.get('/retrieval/stats')
  }
}