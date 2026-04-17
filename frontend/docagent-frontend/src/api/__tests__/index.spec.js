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
  const originalFetch = global.fetch

  beforeEach(() => {
    requestMock.get.mockClear()
    requestMock.post.mockClear()
    if (originalFetch) {
      global.fetch = originalFetch
    } else {
      delete global.fetch
    }
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

  it('gets topic tree backed categories from the classification endpoint', async () => {
    vi.resetModules()
    const { api } = await import('@/api')

    api.getCategories()

    expect(requestMock.get).toHaveBeenCalledWith('/classification/categories')
  })

  it('posts single-document classification requests to the classification endpoint', async () => {
    vi.resetModules()
    const { api } = await import('@/api')

    api.classifyDocument('doc-1')

    expect(requestMock.post).toHaveBeenCalledWith('/classification/classify', { document_id: 'doc-1' })
  })

  it('gets graph payloads from the topics endpoint', async () => {
    vi.resetModules()
    const { api } = await import('@/api')

    api.getGraph({ doc_ids: ['doc-1'], limit: 20 })

    expect(requestMock.get).toHaveBeenCalledWith('/topics/graph', {
      params: { doc_ids: ['doc-1'], limit: 20 },
    })
  })

  it('streams qa responses from the qa endpoint', async () => {
    vi.resetModules()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader() {
          let delivered = false
          return {
            async read() {
              if (delivered) {
                return { done: true, value: undefined }
              }
              delivered = true
              return {
                done: false,
                value: new TextEncoder().encode(
                  'data: {"chunk":"联邦学习通过参数聚合保护隐私。"}\n\n' +
                  'data: {"status":"complete","session_id":"session-1"}\n\n'
                ),
              }
            },
          }
        },
      },
    })
    global.fetch = fetchMock

    const { api } = await import('@/api')
    const onMessage = vi.fn()
    const onDone = vi.fn()

    const cancel = api.streamQA(
      { query: '联邦学习如何保护隐私', doc_ids: ['doc-1'] },
      { onMessage, onDone }
    )

    expect(typeof cancel).toBe('function')
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/v1/qa/stream', expect.objectContaining({
        method: 'POST',
      }))
      expect(onMessage).toHaveBeenCalledWith({
        chunk: '联邦学习通过参数聚合保护隐私。',
      })
      expect(onDone).toHaveBeenCalledWith({
        session_id: 'session-1',
        status: 'complete',
      })
    })
  })
})
