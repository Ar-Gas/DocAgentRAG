import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  getDirectoryWorkspace: vi.fn(),
  workspaceSearch: vi.fn(),
  getDocumentReader: vi.fn(),
}))

vi.mock('@/api', () => ({
  api: apiMocks,
}))

function createDeferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function createWorkspacePayload(overrides = {}) {
  return {
    data: {
      current_scope: { scope_key: 'root', title: '全局目录' },
      breadcrumbs: [{ label: '全局目录' }],
      tree: [],
      folders: [{ node_id: 'public', label: '公共文档', folder_type: 'visibility' }],
      documents: [],
      search_scope: {
        visibility_scope: null,
        department_id: null,
        business_category_id: null,
      },
      ...overrides,
    },
  }
}

const STUBS = {
  'el-input': true,
  'el-button': true,
  'el-empty': true,
  RouterLink: { template: '<a><slot /></a>' },
  DocumentReader: {
    props: ['reader', 'loading'],
    template: '<div class="reader-stub">{{ reader?.filename || "" }}{{ loading ? " loading" : "" }}</div>',
  },
  DocumentViewerModal: { template: '<div class="viewer-stub" />' },
  DirectorySearchBar: {
    props: ['query', 'loading', 'disabled'],
    emits: ['update:query', 'search', 'reset'],
    template: `
      <div class="search-bar-stub">
        <button class="set-query" @click="!disabled && $emit('update:query', '预算')">set-query</button>
        <button class="search" @click="!disabled && $emit('search')">search</button>
        <button class="reset" @click="!disabled && $emit('reset')">reset</button>
      </div>
    `,
  },
  DirectoryTreePanel: {
    props: ['nodes', 'activeScopeKey', 'disabled'],
    emits: ['select-scope'],
    template: `
      <div class="tree-stub">
        <button
          class="scope-fin"
          @click="!disabled && $emit('select-scope', { visibility_scope: 'department', department_id: 'dept-fin', business_category_id: null })"
        >
          scope-fin
        </button>
        <button
          class="scope-ops"
          @click="!disabled && $emit('select-scope', { visibility_scope: 'department', department_id: 'dept-ops', business_category_id: null })"
        >
          scope-ops
        </button>
      </div>
    `,
  },
  DirectoryContentPanel: {
    props: ['mode', 'folders', 'documents', 'searchDocuments', 'selectedDocumentId', 'disabled'],
    emits: ['open-folder', 'select-document', 'open-viewer'],
    template: `
      <div class="content-stub">
        <div class="folders-text">{{ (folders || []).map((item) => item.label).join(',') }}</div>
        <button class="doc-1" @click="!disabled && $emit('select-document', 'doc-1', 'block-1')">doc-1</button>
        <button class="doc-2" @click="!disabled && $emit('select-document', 'doc-2', 'block-2')">doc-2</button>
      </div>
    `,
  },
}

async function mountDashboardPage() {
  const DashboardPage = (await import('@/pages/DashboardPage.vue')).default
  const wrapper = mount(DashboardPage, {
    global: {
      stubs: STUBS,
    },
  })
  await flushPromises()
  return wrapper
}

describe('DashboardPage', () => {
  beforeEach(() => {
    apiMocks.getDirectoryWorkspace.mockResolvedValue(createWorkspacePayload())
    apiMocks.workspaceSearch.mockResolvedValue({
      data: { documents: [], total_documents: 0 },
    })
    apiMocks.getDocumentReader.mockResolvedValue({ data: null })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads the global directory workspace on mount', async () => {
    const wrapper = await mountDashboardPage()

    expect(apiMocks.getDirectoryWorkspace).toHaveBeenCalledWith(
      {},
      expect.objectContaining({ signal: expect.any(Object) }),
    )
    expect(wrapper.text()).toContain('公共文档')
  })

  it('blocks search/tree/document actions while workspace transition is pending', async () => {
    const deferred = createDeferred()
    apiMocks.getDirectoryWorkspace.mockReturnValueOnce(deferred.promise)

    const wrapper = await mountDashboardPage()
    await wrapper.find('.set-query').trigger('click')
    await wrapper.find('.search').trigger('click')
    await wrapper.find('.scope-fin').trigger('click')
    await wrapper.find('.doc-1').trigger('click')
    await flushPromises()

    expect(apiMocks.getDirectoryWorkspace).toHaveBeenCalledTimes(1)
    expect(apiMocks.workspaceSearch).not.toHaveBeenCalled()
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()

    deferred.resolve(createWorkspacePayload())
    await flushPromises()

    expect(wrapper.vm.workspace.current_scope.scope_key).toBe('root')
  })

  it('uses current workspace search_scope in scoped search payload', async () => {
    apiMocks.getDirectoryWorkspace.mockResolvedValueOnce(
      createWorkspacePayload({
        search_scope: {
          visibility_scope: 'department',
          department_id: 'dept-fin',
          business_category_id: 'cat-budget',
        },
      }),
    )
    const wrapper = await mountDashboardPage()

    await wrapper.find('.set-query').trigger('click')
    await wrapper.find('.search').trigger('click')
    await flushPromises()

    expect(apiMocks.workspaceSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        query: '预算',
        visibility_scope: 'department',
        department_id: 'dept-fin',
        business_category_id: 'cat-budget',
      }),
      expect.objectContaining({ signal: expect.any(Object) }),
    )
  })

  it('blocks tree/document/reset actions while scoped search is pending', async () => {
    const deferred = createDeferred()
    apiMocks.workspaceSearch.mockReturnValueOnce(deferred.promise)

    const wrapper = await mountDashboardPage()
    await wrapper.find('.set-query').trigger('click')
    await wrapper.find('.search').trigger('click')
    await flushPromises()

    await wrapper.find('.scope-fin').trigger('click')
    await wrapper.find('.doc-1').trigger('click')
    await wrapper.find('.reset').trigger('click')
    await flushPromises()

    deferred.resolve({
      data: {
        documents: [{ document_id: 'doc-live', filename: '当前文档.pdf' }],
        total_documents: 1,
      },
    })
    await flushPromises()

    expect(apiMocks.getDirectoryWorkspace).toHaveBeenCalledTimes(1)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
    expect(wrapper.vm.searchDocuments).toEqual([{ document_id: 'doc-live', filename: '当前文档.pdf' }])
    expect(wrapper.vm.contentMode).toBe('search')
  })

  it('ignores late reader responses after selecting a newer document', async () => {
    const deferred = createDeferred()
    apiMocks.getDocumentReader
      .mockReturnValueOnce(deferred.promise)
      .mockResolvedValueOnce({
        data: { filename: '第二份文档.pdf', blocks: [] },
      })

    const wrapper = await mountDashboardPage()
    await wrapper.find('.doc-1').trigger('click')
    await wrapper.find('.doc-2').trigger('click')
    await flushPromises()

    deferred.resolve({
      data: { filename: '第一份文档.pdf', blocks: [] },
    })
    await flushPromises()

    expect(wrapper.vm.selectedDocumentId).toBe('doc-2')
    expect(wrapper.vm.readerPayload?.filename).toBe('第二份文档.pdf')
  })

  it('keeps deterministic state when scoped search fails', async () => {
    apiMocks.workspaceSearch.mockRejectedValueOnce(new Error('search failed'))
    const wrapper = await mountDashboardPage()

    await wrapper.find('.set-query').trigger('click')
    await wrapper.find('.search').trigger('click')
    await flushPromises()

    expect(wrapper.vm.searchLoading).toBe(false)
    expect(wrapper.vm.searchDocuments).toEqual([])
    expect(wrapper.vm.contentMode).toBe('directory')
  })
})
