import { beforeEach, describe, expect, it, vi } from 'vitest'

const requestMock = {
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  },
}

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => requestMock),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn() },
}))

describe('api topic tree helpers', () => {
  beforeEach(() => {
    requestMock.get.mockClear()
    requestMock.post.mockClear()
  })

  it('posts topic tree rebuilds to the build endpoint', async () => {
    vi.resetModules()
    const { api } = await import('@/api')

    api.buildTopicTree(true)

    expect(requestMock.post).toHaveBeenCalledWith('/classification/topic-tree/build', { force_rebuild: true })
  })

  it('posts governed upload metadata as multipart fields', async () => {
    vi.resetModules()
    const { api } = await import('@/api')
    const file = new File(['budget'], 'budget.pdf', { type: 'application/pdf' })
    const onProgress = vi.fn()

    api.uploadFile(
      file,
      {
        visibility_scope: 'department',
        owner_department_id: 'dept-fin',
        shared_department_ids: ['dept-ops'],
        business_category_id: 'cat-budget',
        role_restriction: 'department_admin',
        confidentiality_level: 'confidential',
        document_status: 'published',
      },
      onProgress,
    )

    const [url, formData, config] = requestMock.post.mock.calls[0]
    expect(url).toBe('/documents/upload')
    expect(formData).toBeInstanceOf(FormData)
    expect(formData.get('visibility_scope')).toBe('department')
    expect(formData.get('owner_department_id')).toBe('dept-fin')
    expect(formData.get('shared_department_ids')).toBe('["dept-ops"]')
    expect(formData.get('business_category_id')).toBe('cat-budget')
    expect(formData.get('role_restriction')).toBe('department_admin')
    expect(formData.get('confidentiality_level')).toBe('confidential')
    expect(formData.get('document_status')).toBe('published')
    expect(config.onUploadProgress).toBe(onProgress)
  })

  it('uses the governed category endpoints', async () => {
    vi.resetModules()
    const { api } = await import('@/api')

    api.getSystemCategories()
    api.getDepartmentCategories('dept-fin')

    expect(requestMock.get).toHaveBeenCalledWith('/categories/system')
    expect(requestMock.get).toHaveBeenCalledWith('/categories/department', {
      params: { department_id: 'dept-fin' },
    })
  })
})
