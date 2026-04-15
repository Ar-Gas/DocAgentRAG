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
})
