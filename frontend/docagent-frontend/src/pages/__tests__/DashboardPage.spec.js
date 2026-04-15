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

describe('DashboardPage', () => {
  beforeEach(() => {
    apiMocks.getDirectoryWorkspace.mockResolvedValue({
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
      },
    })
    apiMocks.workspaceSearch.mockResolvedValue({
      data: { documents: [], total_documents: 0 },
    })
    apiMocks.getDocumentReader.mockResolvedValue({ data: null })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads the global directory workspace on mount', async () => {
    const DashboardPage = (await import('@/pages/DashboardPage.vue')).default
    const wrapper = mount(DashboardPage, {
      global: {
        stubs: {
          'el-input': true,
          'el-button': true,
          'el-empty': true,
          RouterLink: { template: '<a><slot /></a>' },
          DocumentReader: { template: '<div class="reader-stub" />' },
          DocumentViewerModal: { template: '<div class="viewer-stub" />' },
        },
      },
    })

    await flushPromises()

    expect(apiMocks.getDirectoryWorkspace).toHaveBeenCalledWith({})
    expect(wrapper.text()).toContain('公共文档')
  })
})
