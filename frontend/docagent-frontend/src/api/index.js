import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
})

request.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

// 响应拦截器：统一解包 data 字段，统一错误提示
request.interceptors.response.use(
  response => response.data,
  error => {
    const msg =
      error.response?.data?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '请求失败'
    ElMessage.error(msg)
    return Promise.reject(new Error(msg))
  }
)

export const api = {
  // 文档管理
  uploadFile: (file, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    return request.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000, // 大文件上传允许 5 分钟
      onUploadProgress: onProgress
    })
  },
  getDocumentList: (page = 1, pageSize = 100) => {
    return request.get('/documents/', { params: { page, page_size: pageSize } })
  },
  getDocumentContent: (documentId) => {
    return request.get(`/documents/${documentId}/content`)
  },
  getDocumentReader: (documentId, query = '', anchorBlockId = null) => {
    return request.get(`/documents/${documentId}/reader`, {
      params: { query, anchor_block_id: anchorBlockId }
    })
  },
  deleteDocument: (documentId) => {
    return request.delete(`/documents/${documentId}`)
  },
  rechunkDocument: (documentId, useRefiner = true) => {
    return request.post(`/documents/${documentId}/rechunk`, { use_refiner: useRefiner })
  },

  // 文档分类
  classifyDocument: (documentId) => {
    return request.post('/classification/classify', { document_id: documentId })
  },
  reclassifyDocument: (documentId) => {
    return request.post(`/classification/reclassify/${documentId}`)
  },
  getCategories: () => {
    return request.get('/classification/categories')
  },
  getDocumentsByCategory: (category) => {
    return request.get(`/classification/documents/${category}`)
  },

  // 语义主题树
  getTopicTree: () => {
    return request.get('/classification/topic-tree')
  },
  buildTopicTree: (forceRebuild = false) => {
    return request.post('/classification/topic-tree/build', { force_rebuild: forceRebuild })
  },

  // 原文件预览：返回文件访问 URL（不发请求，直接拼 URL）
  getDocumentFileUrl: (documentId) => `/api/v1/documents/${documentId}/file`,

  // 文档检索
  workspaceSearch: (payload) => {
    return request.post('/retrieval/workspace-search', payload)
  },
  getStats: () => {
    return request.get('/retrieval/stats')
  },
  summarizeResults: (query, results = []) => {
    return request.post('/retrieval/summarize-results', { query, results })
  },
  generateClassificationTable: (query, results = [], persist = false) => {
    return request.post('/classification/tables/generate', { query, results, persist })
  }
}

/**
 * Smart Search SSE — 两阶段流式检索
 * @returns {Function} cancel 取消函数
 */
export function workspaceSearchStream(payload, { onResults, onReranked, onDone, onError } = {}) {
  const ctrl = new AbortController()

  fetch('/api/v1/retrieval/workspace-search-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: ctrl.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''

        for (const frame of frames) {
          let eventName = ''
          let dataStr = ''
          for (const line of frame.split('\n')) {
            if (line.startsWith('event: ')) eventName = line.slice(7).trim()
            if (line.startsWith('data: ')) dataStr = line.slice(6)
          }
          if (!eventName) continue
          try {
            const parsed = JSON.parse(dataStr || '{}')
            if (eventName === 'results') onResults?.(parsed)
            else if (eventName === 'reranked') onReranked?.(parsed)
            else if (eventName === 'done') onDone?.()
            else if (eventName === 'error' || eventName === 'rerank_error') onError?.(new Error(parsed.error))
          } catch (_) {
            // JSON 解析失败忽略
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError?.(err)
    })

  return () => ctrl.abort()
}
