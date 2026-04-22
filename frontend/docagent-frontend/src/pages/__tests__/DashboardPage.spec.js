import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getDocumentList: vi.fn(),
  getStats: vi.fn(),
}))

vi.mock('@/api', () => ({ api }))

const STUBS = {
  RouterLink: {
    props: ['to'],
    template: '<a><slot /></a>',
  },
  DocumentViewerModal: {
    template: '<div class="viewer-modal-stub" />',
  },
  ElIcon: {
    template: '<span><slot /></span>',
  },
  ElTable: {
    props: ['data'],
    template: '<div><slot /><div v-for="row in data" :key="row.id">{{ row.filename }}</div></div>',
  },
  ElTableColumn: {
    template: '<div />',
  },
}

describe('DashboardPage', () => {
  beforeEach(() => {
    api.getDocumentList.mockResolvedValue({
      data: {
        items: [
          {
            id: 'doc-1',
            filename: '预算制度.pdf',
            file_type: '.pdf',
            created_at_iso: '2026-04-20T12:00:00',
            classification_result: '财务制度',
          },
        ],
        total: 1,
      },
    })
    api.getStats.mockResolvedValue({
      data: {
        total_chunks: 12,
        file_types: { '.pdf': 12 },
      },
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders recent documents even when retrieval stats fails', async () => {
    api.getStats.mockRejectedValueOnce(new Error('stats timeout'))

    const DashboardPage = (await import('@/pages/DashboardPage.vue')).default
    const wrapper = mount(DashboardPage, {
      global: {
        stubs: STUBS,
      },
    })

    await flushPromises()

    expect(api.getDocumentList).toHaveBeenCalledWith(1, 20)
    expect(api.getStats).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('预算制度.pdf')
    expect(wrapper.text()).toContain('1')
  }, 20000)
})
