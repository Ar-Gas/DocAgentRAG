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

vi.mock('@/api', () => ({
  api: apiMocks,
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

function createDeferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function mountSearchPage() {
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
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('presents concrete retrieval and keeps semantic surfaces removed', async () => {
    const wrapper = await mountSearchPage()

    expect(wrapper.text()).toContain('具体检索')
    expect(wrapper.text()).not.toContain('主题树')
    expect(wrapper.text()).not.toContain('摘要报告')
    expect(wrapper.text()).not.toContain('分类报告')
    expect(apiMocks.getStats).toHaveBeenCalledTimes(1)
    expect(apiMocks.getDepartments).toHaveBeenCalledTimes(1)
    expect(apiMocks.getSystemCategories).toHaveBeenCalledTimes(1)
    expect(apiMocks.getDepartmentCategories).not.toHaveBeenCalled()
  })

  it('sends only concrete governance filters in workspace search payloads', async () => {
    const wrapper = await mountSearchPage()

    wrapper.vm.filters.query = '预算审批'
    wrapper.vm.filters.mode = 'smart'
    wrapper.vm.filters.visibility_scope = 'department'
    wrapper.vm.filters.department_id = 'dept-fin'
    wrapper.vm.filters.business_category_id = 'cat-budget'
    wrapper.vm.filters.file_types = ['pdf']
    wrapper.vm.filters.filename = '预算手册'
    wrapper.vm.filters.date_range = ['2026-01-01', '2026-02-01']
    wrapper.vm.filters.limit = 20
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    const payload = apiMocks.workspaceSearch.mock.calls[0][0]
    expect(payload).toEqual({
      query: '预算审批',
      mode: 'hybrid',
      visibility_scope: 'department',
      department_id: 'dept-fin',
      business_category_id: 'cat-budget',
      limit: 20,
      file_types: ['pdf'],
      filename: '预算手册',
      date_from: '2026-01-01',
      date_to: '2026-02-01',
      group_by_document: true,
    })
    expect(payload.use_query_expansion).toBeUndefined()
    expect(payload.use_llm_rerank).toBeUndefined()
    expect(payload.expansion_method).toBeUndefined()
  })

  it('resets the current workspace without semantic drawer state', async () => {
    const wrapper = await mountSearchPage()

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

  it('ignores late workspace responses after reset', async () => {
    const deferred = createDeferred()
    apiMocks.workspaceSearch.mockReturnValueOnce(deferred.promise)

    const wrapper = await mountSearchPage()

    wrapper.vm.filters.query = '预算'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    await wrapper.find('.reset').trigger('click')
    deferred.resolve({
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
  })

  it('ignores late workspace responses after unmount', async () => {
    const deferred = createDeferred()
    apiMocks.workspaceSearch.mockReturnValueOnce(deferred.promise)

    const wrapper = await mountSearchPage()

    wrapper.vm.filters.query = '预算'
    await wrapper.find('.go').trigger('click')
    await flushPromises()

    wrapper.unmount()
    deferred.resolve({
      data: {
        results: [{ id: 'res-1' }],
        documents: [{ document_id: 'doc-late' }],
        total_results: 1,
        total_documents: 1,
        applied_filters: {},
      },
    })
    await flushPromises()

    expect(apiMocks.workspaceSearch).toHaveBeenCalledTimes(1)
  })

  it('ignores stale reader response after a newer document selection', async () => {
    const older = createDeferred()
    const newer = createDeferred()
    apiMocks.getDocumentReader
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise)

    const wrapper = await mountSearchPage()
    wrapper.vm.workspace = {
      results: [],
      documents: [
        { document_id: 'doc-old', best_block_id: 'b-old' },
        { document_id: 'doc-new', best_block_id: 'b-new' },
      ],
      total_results: 0,
      total_documents: 2,
      applied_filters: {},
    }

    const oldPromise = wrapper.vm.selectDocument('doc-old')
    const newPromise = wrapper.vm.selectDocument('doc-new')

    newer.resolve({ data: { filename: 'newer.docx' } })
    await flushPromises()

    expect(wrapper.vm.selectedDocumentId).toBe('doc-new')
    expect(wrapper.vm.readerPayload).toEqual({ filename: 'newer.docx' })

    older.resolve({ data: { filename: 'older.docx' } })
    await flushPromises()
    await Promise.allSettled([oldPromise, newPromise])

    expect(wrapper.vm.selectedDocumentId).toBe('doc-new')
    expect(wrapper.vm.readerPayload).toEqual({ filename: 'newer.docx' })
  })

  it('keeps stable empty workspace when workspace search request fails', async () => {
    apiMocks.workspaceSearch.mockRejectedValueOnce(new Error('search failed'))

    const wrapper = await mountSearchPage()
    wrapper.vm.workspace = {
      results: [{ id: 'res-1' }],
      documents: [{ document_id: 'doc-1' }],
      total_results: 1,
      total_documents: 1,
      applied_filters: {},
    }
    wrapper.vm.selectedDocumentId = 'doc-1'
    wrapper.vm.readerPayload = { filename: 'doc-1.pdf' }

    await expect(wrapper.vm.executeSearch()).resolves.toBeUndefined()

    expect(wrapper.vm.workspace).toEqual({
      results: [],
      documents: [],
      total_results: 0,
      total_documents: 0,
      applied_filters: {},
    })
    expect(wrapper.vm.selectedDocumentId).toBe('')
    expect(wrapper.vm.readerPayload).toBeNull()
    expect(wrapper.vm.searchLoading).toBe(false)
  })

  it('keeps reader cleared and stable when reader request fails', async () => {
    apiMocks.getDocumentReader.mockRejectedValueOnce(new Error('reader failed'))

    const wrapper = await mountSearchPage()
    wrapper.vm.workspace = {
      results: [],
      documents: [{ document_id: 'doc-2', best_block_id: 'b2' }],
      total_results: 0,
      total_documents: 1,
      applied_filters: {},
    }
    wrapper.vm.readerPayload = { filename: 'stale.pdf' }

    await expect(wrapper.vm.selectDocument('doc-2')).resolves.toBeUndefined()

    expect(wrapper.vm.selectedDocumentId).toBe('doc-2')
    expect(wrapper.vm.readerPayload).toBeNull()
    expect(wrapper.vm.readerLoading).toBe(false)
  })
})
