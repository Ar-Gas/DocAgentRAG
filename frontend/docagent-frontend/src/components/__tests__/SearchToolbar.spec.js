import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SearchToolbar from '@/components/SearchToolbar.vue'

describe('SearchToolbar', () => {
  it('describes vector mode without legacy semantic wording', () => {
    const wrapper = mount(SearchToolbar, {
      props: {
        modelValue: {
          mode: 'vector',
        },
        stats: {
          file_types: {},
        },
        departments: [],
        categories: [],
        loading: false,
      },
      global: {
        stubs: {
          ElInput: true,
          ElSelect: {
            template: '<div><slot /></div>',
          },
          ElOption: true,
          ElDatePicker: true,
          ElButton: {
            template: '<button><slot /></button>',
          },
        },
      },
    })

    const description = wrapper.find('.mode-note p').text()
    expect(description).toContain('内容')
    expect(description).not.toContain('语义')
  })
})
