import axios from 'axios'
import { ElMessage } from 'element-plus'

import { sessionStore } from '@/stores/session'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

function redirectToLogin() {
  if (typeof window === 'undefined') {
    return
  }

  const redirectTarget =
    window.location.pathname === '/login'
      ? '/login'
      : `/login?redirect=${encodeURIComponent(
          `${window.location.pathname}${window.location.search || ''}`,
        )}`

  window.location.assign(redirectTarget)
}

function handleUnauthorized() {
  sessionStore.clear()
  redirectToLogin()
}

request.interceptors.request.use(
  (config) => {
    if (sessionStore.state.token) {
      config.headers = config.headers || {}
      config.headers.Authorization = `Bearer ${sessionStore.state.token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      handleUnauthorized()
    }

    const msg =
      error.response?.data?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '请求失败'

    ElMessage.error(msg)
    const wrappedError = new Error(msg)
    wrappedError.status = error.response?.status || null
    return Promise.reject(wrappedError)
  },
)

export const api = {
  login: (payload) => request.post('/auth/login', payload),
  logout: () => request.post('/auth/logout'),
  getCurrentUser: () => request.get('/auth/me'),
  changePassword: (payload) => request.post('/auth/change-password', payload),
  getDepartments: () => request.get('/departments'),
  getRoles: () => request.get('/roles'),
  getUsers: (page = 1, pageSize = 10) =>
    request.get('/users', { params: { page, page_size: pageSize } }),
  createUser: (payload) => request.post('/users', payload),
  getDirectoryWorkspace: (params = {}) =>
    request.get('/directory/workspace', { params }),
  uploadFile: (file, metadata = {}, onProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('visibility_scope', metadata.visibility_scope || 'department')
    formData.append('owner_department_id', metadata.owner_department_id || '')
    formData.append(
      'shared_department_ids',
      JSON.stringify(metadata.shared_department_ids || []),
    )
    formData.append('business_category_id', metadata.business_category_id || '')
    formData.append('role_restriction', metadata.role_restriction || '')
    formData.append('confidentiality_level', metadata.confidentiality_level || 'internal')
    formData.append('document_status', metadata.document_status || 'draft')
    return request.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
      onUploadProgress: onProgress,
    })
  },
  getDocumentList: (page = 1, pageSize = 100) =>
    request.get('/documents/', { params: { page, page_size: pageSize } }),
  getDocumentReader: (documentId, query = '', anchorBlockId = null) =>
    request.get(`/documents/${documentId}/reader`, {
      params: { query, anchor_block_id: anchorBlockId },
    }),
  deleteDocument: (documentId) => request.delete(`/documents/${documentId}`),
  getSystemCategories: () => request.get('/categories/system'),
  getDepartmentCategories: (departmentId) =>
    request.get('/categories/department', {
      params: { department_id: departmentId },
    }),
  createSystemCategory: (payload) => request.post('/categories/system', payload),
  createDepartmentCategory: (payload) => request.post('/categories/department', payload),
  updateCategory: (categoryId, payload) => request.patch(`/categories/${categoryId}`, payload),
  workspaceSearch: (payload) => request.post('/retrieval/workspace-search', payload),
  getStats: () => request.get('/retrieval/stats'),
  getAuditLogs: (params = {}) => request.get('/audit-logs', { params }),
}

export function workspaceSearchStream(payload, { onResults, onReranked, onDone, onError } = {}) {
  const ctrl = new AbortController()
  const headers = { 'Content-Type': 'application/json' }

  if (sessionStore.state.token) {
    headers.Authorization = `Bearer ${sessionStore.state.token}`
  }

  fetch('/api/v1/retrieval/workspace-search-stream', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal: ctrl.signal,
  })
    .then(async (res) => {
      if (res.status === 401) {
        handleUnauthorized()
        throw new Error('登录已失效，请重新登录')
      }

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
            else if (eventName === 'error' || eventName === 'rerank_error') {
              onError?.(new Error(parsed.error))
            }
          } catch (_error) {
            // Ignore malformed SSE frames.
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        onError?.(error)
      }
    })

  return () => ctrl.abort()
}
