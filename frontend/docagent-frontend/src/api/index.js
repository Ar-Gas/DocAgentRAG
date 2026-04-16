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
    if (
      axios.isCancel(error) ||
      error?.code === 'ERR_CANCELED' ||
      error?.name === 'CanceledError'
    ) {
      return Promise.reject(error)
    }

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
  getDirectoryWorkspace: (params = {}, config = {}) =>
    request.get('/directory/workspace', { params, ...config }),
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
  getDocumentFileBlob: (documentId) =>
    request.get(`/documents/${documentId}/file`, { responseType: 'blob' }),
  getDocumentReader: (documentId, query = '', anchorBlockId = null, config = {}) =>
    request.get(`/documents/${documentId}/reader`, {
      params: { query, anchor_block_id: anchorBlockId },
      ...config,
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
  workspaceSearch: (payload, config = {}) => request.post('/retrieval/workspace-search', payload, config),
  getStats: () => request.get('/retrieval/stats'),
  getAuditLogs: (params = {}) => request.get('/audit-logs', { params }),
}
