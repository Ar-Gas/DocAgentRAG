import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getDocumentList: vi.fn().mockResolvedValue({
    data: {
      items: [
        { id: 'doc-1', filename: '联邦学习白皮书.pdf', file_type: '.pdf' },
        { id: 'doc-2', filename: '差分隐私综述.docx', file_type: '.docx' },
      ],
    },
  }),
  streamQA: vi.fn((_payload, handlers = {}) => {
    handlers.onMessage?.({ chunk: '联邦学习通过参数聚合降低原始数据暴露风险。' })
    handlers.onDone?.({ status: 'complete', session_id: 'session-1' })
    return () => {}
  }),
}))

vi.mock('@/api', () => ({ api }))

describe('QAPage', () => {
  it('loads documents and streams answers into the session panel', async () => {
    const QAPage = (await import('@/pages/QAPage.vue')).default
    const wrapper = mount(QAPage)

    await flushPromises()
    expect(wrapper.text()).toContain('联邦学习白皮书.pdf')

    await wrapper.find('.qa-question-input').setValue('联邦学习如何保护隐私？')
    await wrapper.find('.qa-submit-btn').trigger('click')
    await flushPromises()

    expect(api.streamQA).toHaveBeenCalledWith(
      expect.objectContaining({
        query: '联邦学习如何保护隐私？',
      }),
      expect.any(Object)
    )
    expect(wrapper.text()).toContain('联邦学习通过参数聚合降低原始数据暴露风险。')
  })
})
