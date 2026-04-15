import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  workspaceSearch: vi.fn(),
  getStats: vi.fn(),
  getDepartments: vi.fn(),
  getSystemCategories: vi.fn(),
  getDepartmentCategories: vi.fn(),
  getDocumentReader: vi.fn(),
}))

const streamState = vi.hoisted(() => ({
  cancel: vi.fn(),
  callbacks: null,
}))

const workspaceSearchStream = vi.hoisted(() =>
  vi.fn((_payload, callbacks) => {
    streamState.callbacks = callbacks
    return streamState.cancel
  }),
)
const SEARCH_PAGE_TEST_TIMEOUT = 10000

vi.mock('@/api', () => ({
  api: apiMocks,
  workspaceSearchStream,
}))

const STUBS = {
  SearchToolbar: {
    props: ['modelValue'],
    emits: ['update:modelValue', 'search', 'reset'],
    template: `
      <div>
        <button class="go" @click="$emit('search')">go</button>
        <button class="reset" @click="$emit('reset')">reset</button>
      </div>
    `,
  },
  DocumentResultList: { template: '<div class="result-list-stub" />' },
  DocumentReader: { template: '<div class="reader-stub" />' },
  DocumentViewerModal: { template: '<div class="viewer-modal-stub" />' },
}

async function mountSearchPage(version = 'block') {
  vi.stubEnv('VITE_WORKSPACE_RETRIEVAL_VERSION', version)
  vi.resetModules()
  const SearchPage = (await import('@/pages/SearchPage.vue')).default

  const wrapper = mount(SearchPage, {
    global: {
      stubs: STUBS,
    },
  })

  await flushPromises()
  return wrapper
}

describe('SearchPage', () => {
  beforeEach(() => {
    apiMocks.workspaceSearch.mockResolvedValue({
      data: {
        results: [],
        documents: [],
        total_results: 0,
        total_documents: 0,
        applied_filters: {},
      },
    })
    apiMocks.getStats.mockResolvedValue({ data: {} })
    apiMocks.getDepartments.mockResolvedValue({ data: [] })
    apiMocks.getSystemCategories.mockResolvedValue({ data: [] })
    apiMocks.getDepartmentCategories.mockResolvedValue({ data: [] })
    apiMocks.getDocumentReader.mockResolvedValue({ data: null })
    workspaceSearchStream.mockClear()
    streamState.cancel.mockClear()
    streamState.callbacks = null
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllEnvs()
  })

  it('loads the reduced search chrome without semantic dependencies', async () => {
    await mountSearchPage('block')

    expect(apiMocks.getStats).toHaveBeenCalledTimes(1)
    expect(apiMocks.getDepartments).toHaveBeenCalledTimes(1)
    expect(apiMocks.getSystemCategories).toHaveBeenCalledTimes(1)
    expect(apiMocks.getDepartmentCategories).not.toHaveBeenCalled()
  })

  it('uses sync workspace search for block smart requests', async () => {
    const wrapper = await mountSearchPage('block')

    wrapper.vm.filters.mode = 'smart'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    expect(apiMocks.workspaceSearch).toHaveBeenCalledWith(expect.objectContaining({
      mode: 'smart',
      retrieval_version: 'block',
    }))
    expect(workspaceSearchStream).not.toHaveBeenCalled()
  }, SEARCH_PAGE_TEST_TIMEOUT)

  it('keeps legacy smart requests on the SSE path during rollout', async () => {
    const wrapper = await mountSearchPage('legacy')

    wrapper.vm.filters.mode = 'smart'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    expect(workspaceSearchStream).toHaveBeenCalledWith(expect.objectContaining({
      mode: 'smart',
      retrieval_version: 'legacy',
    }), expect.any(Object))
    expect(apiMocks.workspaceSearch).not.toHaveBeenCalled()
  }, SEARCH_PAGE_TEST_TIMEOUT)

  it('includes visibility and department filters in workspace search requests', async () => {
    const wrapper = await mountSearchPage('block')

    wrapper.vm.filters.visibility_scope = 'department'
    wrapper.vm.filters.department_id = 'dept-fin'
    wrapper.vm.filters.business_category_id = 'cat-budget'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    expect(apiMocks.workspaceSearch).toHaveBeenCalledWith(expect.objectContaining({
      visibility_scope: 'department',
      department_id: 'dept-fin',
      business_category_id: 'cat-budget',
    }))
  }, SEARCH_PAGE_TEST_TIMEOUT)

  it('resets the current workspace without semantic drawer state', async () => {
    const wrapper = await mountSearchPage('block')

    wrapper.vm.filters.query = '预算'
    wrapper.vm.filters.department_id = 'dept-fin'
    wrapper.vm.workspace = {
      results: [],
      documents: [{ document_id: 'doc-1' }],
      total_results: 1,
      total_documents: 1,
      applied_filters: {},
    }
    wrapper.vm.selectedDocumentId = 'doc-1'
    wrapper.vm.readerPayload = { filename: 'budget.pdf' }

    await wrapper.find('.reset').trigger('click')
    await flushPromises()

    expect(wrapper.vm.filters.query).toBe('')
    expect(wrapper.vm.filters.department_id).toBe('')
    expect(wrapper.vm.workspace.documents).toEqual([])
    expect(wrapper.vm.selectedDocumentId).toBe('')
    expect(wrapper.vm.readerPayload).toBeNull()
  })

  it('cancels active legacy smart-search streams on reset and ignores late callbacks', async () => {
    const wrapper = await mountSearchPage('legacy')

    wrapper.vm.filters.mode = 'smart'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    expect(streamState.callbacks).toBeTruthy()

    await wrapper.find('.reset').trigger('click')
    await flushPromises()

    expect(streamState.cancel).toHaveBeenCalledTimes(1)

    await streamState.callbacks.onResults({
      data: {
        results: [{ id: 'res-1' }],
        documents: [{ document_id: 'doc-late' }],
        total_results: 1,
        total_documents: 1,
        applied_filters: {},
      },
    })
    await flushPromises()

    expect(wrapper.vm.workspace.documents).toEqual([])
    expect(wrapper.vm.workspace.total_documents).toBe(0)
    expect(wrapper.vm.selectedDocumentId).toBe('')
  }, SEARCH_PAGE_TEST_TIMEOUT)

  it('cancels active legacy smart-search streams on unmount', async () => {
    const wrapper = await mountSearchPage('legacy')

    wrapper.vm.filters.mode = 'smart'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    expect(streamState.callbacks).toBeTruthy()

    wrapper.unmount()

    expect(streamState.cancel).toHaveBeenCalledTimes(1)
  }, SEARCH_PAGE_TEST_TIMEOUT)
})
