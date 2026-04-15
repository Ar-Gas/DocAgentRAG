import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  workspaceSearch: vi.fn(),
  getStats: vi.fn(),
  getCategories: vi.fn(),
  getDepartments: vi.fn(),
  getSystemCategories: vi.fn(),
  getDepartmentCategories: vi.fn(),
  getTopicTree: vi.fn(),
  summarizeResults: vi.fn(),
  generateClassificationTable: vi.fn(),
  buildTopicTree: vi.fn(),
  getDocumentReader: vi.fn(),
}))

const workspaceSearchStream = vi.hoisted(() => vi.fn(() => () => {}))

vi.mock('@/api', () => ({
  api: apiMocks,
  workspaceSearchStream,
}))

const STUBS = {
  SearchToolbar: {
    props: ['modelValue'],
    emits: ['update:modelValue', 'search', 'reset', 'summarize', 'generate-report', 'rebuild-topics'],
    template: '<button class="go" @click="$emit(\'search\')">go</button>',
  },
  DocumentResultList: { template: '<div class="result-list-stub" />' },
  DocumentReader: { template: '<div class="reader-stub" />' },
  SummaryDrawer: { template: '<div class="summary-drawer-stub" />' },
  ClassificationReportDrawer: { template: '<div class="classification-drawer-stub" />' },
  TopicTreePanel: { template: '<div class="topic-tree-stub" />' },
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
    apiMocks.getCategories.mockResolvedValue({ data: { categories: [] } })
    apiMocks.getDepartments.mockResolvedValue({ data: [] })
    apiMocks.getSystemCategories.mockResolvedValue({ data: [] })
    apiMocks.getDepartmentCategories.mockResolvedValue({ data: [] })
    apiMocks.getTopicTree.mockResolvedValue({ data: { topics: [], total_documents: 0 } })
    apiMocks.summarizeResults.mockResolvedValue({ data: null })
    apiMocks.generateClassificationTable.mockResolvedValue({ data: null })
    apiMocks.buildTopicTree.mockResolvedValue({ data: { topics: [], total_documents: 0 } })
    apiMocks.getDocumentReader.mockResolvedValue({ data: null })
    workspaceSearchStream.mockClear()
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllEnvs()
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
  })

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
  })

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
  })
})
