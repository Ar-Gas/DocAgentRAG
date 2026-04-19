import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import RagStudioPage from '@/pages/RagStudioPage.vue'

describe('RagStudioPage', () => {
  it('embeds proxied LightRAG webui through same-origin route', () => {
    const wrapper = mount(RagStudioPage)

    const frame = wrapper.get('iframe')
    expect(frame.attributes('src')).toBe('/api/v1/admin/lightrag/webui/')
    expect(wrapper.text()).toContain('RAG 工作台')
  })
})
