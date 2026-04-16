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
    requestMock.post.mockClear()
  })

  it('posts topic tree rebuilds to the build endpoint', async () => {
    vi.resetModules()
    const { api } = await import('@/api')

    api.buildTopicTree(true)

    expect(requestMock.post).toHaveBeenCalledWith('/classification/topic-tree/build', { force_rebuild: true })
  })

  it('posts workspace search payload without injecting retrieval_version', async () => {
    vi.resetModules()
    const { api } = await import('@/api')
    const payload = { query: '预算', mode: 'hybrid', limit: 10 }

    api.workspaceSearch(payload)

    expect(requestMock.post).toHaveBeenCalledWith('/retrieval/workspace-search', payload)
    expect(requestMock.post.mock.calls[0][1]).not.toHaveProperty('retrieval_version')
  })
})
