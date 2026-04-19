import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getGraph: vi.fn().mockResolvedValue({
    data: {
      nodes: [
        { id: 'federated-learning', label: '联邦学习', degree: 3 },
        { id: 'privacy', label: '隐私保护', degree: 2 },
      ],
      edges: [
        {
          from: 'federated-learning',
          to: 'privacy',
          label: '提升',
          doc_id: 'doc-1',
        },
      ],
    },
  }),
}))

vi.mock('@/api', () => ({ api }))

describe('GraphPage', () => {
  it('loads graph payload on mount and renders node labels', async () => {
    const GraphPage = (await import('@/pages/GraphPage.vue')).default
    const wrapper = mount(GraphPage)

    await flushPromises()

    expect(api.getGraph).toHaveBeenCalled()
    expect(wrapper.text()).toContain('联邦学习')
    expect(wrapper.text()).toContain('隐私保护')
    expect(wrapper.text()).toContain('提升')
  })

  it('shows an architecture hint when the graph is empty', async () => {
    api.getGraph.mockResolvedValueOnce({
      data: {
        nodes: [],
        edges: [],
        stats: {
          total_nodes: 0,
          total_edges: 0,
          total_docs: 0,
        },
      },
    })

    const GraphPage = (await import('@/pages/GraphPage.vue')).default
    const wrapper = mount(GraphPage)

    await flushPromises()

    expect(wrapper.text()).toContain('当前知识图谱仍依赖本地 KG 索引')
    expect(wrapper.text()).toContain('尚未同步到本地图谱')
  })
})
