import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getGraphLabels: vi.fn().mockResolvedValue({
    data: {
      items: ['联邦学习', '隐私保护'],
    },
  }),
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

    expect(api.getGraphLabels).toHaveBeenCalled()
    expect(api.getGraph).toHaveBeenCalled()
    expect(api.getGraph).toHaveBeenCalledWith({ label: '联邦学习' })
    expect(wrapper.text()).toContain('联邦学习')
    expect(wrapper.text()).toContain('隐私保护')
    expect(wrapper.text()).toContain('提升')
  })

  it('shows a lightrag empty hint when the graph is empty', async () => {
    api.getGraphLabels.mockResolvedValueOnce({
      data: {
        items: [],
      },
    })
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

    expect(wrapper.text()).toContain('当前 LightRAG 图谱暂无可展示数据')
    expect(wrapper.text()).toContain('请先在 LightRAG 中完成文档入库与实体关系抽取')
  })
})
