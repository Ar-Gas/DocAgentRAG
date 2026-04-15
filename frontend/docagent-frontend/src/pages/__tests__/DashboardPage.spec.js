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
    props: ['query', 'loading'],
    emits: ['update:query', 'search', 'reset'],
    template: `
      <div class="search-bar-stub">
        <button class="set-query" @click="$emit('update:query', '预算')">set-query</button>
        <button class="search" @click="$emit('search')">search</button>
        <button class="reset" @click="$emit('reset')">reset</button>
      </div>
    `,
  },
  DirectoryTreePanel: {
    props: ['nodes', 'activeScopeKey'],
    emits: ['select-scope'],
    template: `
      <div class="tree-stub">
        <button
          class="scope-fin"
          @click="$emit('select-scope', { visibility_scope: 'department', department_id: 'dept-fin', business_category_id: null })"
        >
          scope-fin
        </button>
        <button
          class="scope-ops"
          @click="$emit('select-scope', { visibility_scope: 'department', department_id: 'dept-ops', business_category_id: null })"
        >
          scope-ops
        </button>
      </div>
    `,
  },
  DirectoryContentPanel: {
    props: ['mode', 'folders', 'documents', 'searchDocuments', 'selectedDocumentId'],
    emits: ['open-folder', 'select-document', 'open-viewer'],
    template: `
      <div class="content-stub">
        <div class="folders-text">{{ (folders || []).map((item) => item.label).join(',') }}</div>
        <button class="doc-1" @click="$emit('select-document', 'doc-1', 'block-1')">doc-1</button>
        <button class="doc-2" @click="$emit('select-document', 'doc-2', 'block-2')">doc-2</button>
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

    expect(apiMocks.getDirectoryWorkspace).toHaveBeenCalledWith({})
    expect(wrapper.text()).toContain('公共文档')
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

    expect(apiMocks.workspaceSearch).toHaveBeenCalledWith(expect.objectContaining({
      query: '预算',
      visibility_scope: 'department',
      department_id: 'dept-fin',
      business_category_id: 'cat-budget',
    }))
  })

  it('ignores late scoped-search responses after reset', async () => {
    const deferred = createDeferred()
    apiMocks.workspaceSearch.mockReturnValueOnce(deferred.promise)

    const wrapper = await mountDashboardPage()
    await wrapper.find('.set-query').trigger('click')
    await wrapper.find('.search').trigger('click')
    await flushPromises()

    await wrapper.find('.reset').trigger('click')
    await flushPromises()

    deferred.resolve({
      data: {
        documents: [{ document_id: 'doc-stale', filename: '过期文档.pdf' }],
        total_documents: 1,
      },
    })
    await flushPromises()

    expect(wrapper.vm.searchDocuments).toEqual([])
    expect(wrapper.vm.contentMode).toBe('directory')
  })

  it('ignores late workspace responses after a newer scope action', async () => {
    const deferred = createDeferred()
    apiMocks.getDirectoryWorkspace
      .mockResolvedValueOnce(createWorkspacePayload())
      .mockReturnValueOnce(deferred.promise)
      .mockResolvedValueOnce(
        createWorkspacePayload({
          current_scope: { scope_key: 'department:dept-ops', title: '运营部' },
          breadcrumbs: [{ label: '全局目录' }, { label: '运营部' }],
          folders: [{ node_id: 'ops-root', label: '运营目录', folder_type: 'department' }],
          search_scope: {
            visibility_scope: 'department',
            department_id: 'dept-ops',
            business_category_id: null,
          },
        }),
      )

    const wrapper = await mountDashboardPage()
    await wrapper.find('.scope-fin').trigger('click')
    await wrapper.find('.scope-ops').trigger('click')
    await flushPromises()

    deferred.resolve(
      createWorkspacePayload({
        current_scope: { scope_key: 'department:dept-fin', title: '财务部' },
        breadcrumbs: [{ label: '全局目录' }, { label: '财务部' }],
        folders: [{ node_id: 'fin-root', label: '财务旧目录', folder_type: 'department' }],
      }),
    )
    await flushPromises()

    expect(wrapper.vm.workspace.current_scope.scope_key).toBe('department:dept-ops')
    expect(wrapper.text()).toContain('运营目录')
    expect(wrapper.text()).not.toContain('财务旧目录')
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
