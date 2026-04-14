import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DocumentReader from '@/components/DocumentReader.vue'

describe('DocumentReader', () => {
  it('shows match navigation and switches the active match', async () => {
    const wrapper = mount(DocumentReader, {
      props: {
        loading: false,
        reader: {
          document_id: 'doc-1',
          filename: 'budget-report.pdf',
          total_matches: 2,
          best_anchor: {
            block_id: 'doc-1#0',
            block_index: 0,
            match_index: 0,
            start: 0,
            end: 2,
            term: '预算'
          },
          blocks: [
            {
              block_id: 'doc-1#0',
              block_index: 0,
              block_type: 'paragraph',
              heading_path: ['第三章 财务管理'],
              page_number: 12,
              text: '预算审批流程',
              matches: [{ start: 0, end: 2, term: '预算' }]
            },
            {
              block_id: 'doc-1#1',
              block_index: 1,
              block_type: 'paragraph',
              heading_path: ['第三章 财务管理'],
              page_number: 12,
              text: '预算执行与报销约束',
              matches: [{ start: 0, end: 2, term: '预算' }]
            }
          ]
        }
      },
      attachTo: document.body,
      global: {
        stubs: {
          ElButton: {
            props: ['disabled'],
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
          },
          ElSkeleton: {
            template: '<div class="el-skeleton"></div>'
          },
          ElTag: {
            template: '<span class="el-tag"><slot /></span>'
          },
          ElEmpty: {
            template: '<div class="el-empty"></div>'
          }
        }
      }
    })

    expect(wrapper.text()).toContain('budget-report.pdf')
    expect(wrapper.text()).toContain('第三章 财务管理')
    expect(wrapper.text()).toContain('paragraph')
    expect(wrapper.find('.reader-nav .nav-count').text()).toContain('1 / 2')
    expect(wrapper.findAll('mark').length).toBe(2)
    expect(wrapper.findAll('mark.is-active').length).toBe(1)

    await wrapper.findAll('.reader-nav .nav-button')[1].trigger('click')

    expect(wrapper.find('.reader-nav .nav-count').text()).toContain('2 / 2')
    expect(wrapper.findAll('mark.is-active').length).toBe(1)
  })
})
