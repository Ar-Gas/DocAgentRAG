import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TopicTreePanel from '@/components/TopicTreePanel.vue'

const STUBS = {
  ElTag: { props: ['type', 'size'], template: '<span class="el-tag"><slot /></span>' },
  ElButton: { template: '<button><slot /></button>' },
  ElSkeleton: { template: '<div class="el-skeleton"></div>' },
  ElEmpty: { template: '<div class="el-empty"></div>' },
}

const TREE = {
  total_documents: 2,
  topics: [
    {
      topic_id: 'topic-1',
      label: '财务治理',
      document_count: 2,
      documents: [],
      children: [
        {
          topic_id: 'topic-1-1',
          label: '年度审计',
          document_count: 1,
          documents: [
            { document_id: 'doc-1', filename: 'audit-plan.pdf', file_type: '.pdf' },
          ],
          children: [],
        },
        {
          topic_id: 'topic-1-2',
          label: '供应商比价',
          document_count: 1,
          documents: [
            { document_id: 'doc-2', filename: 'supplier-comparison.xlsx', file_type: '.xlsx' },
          ],
          children: [],
        },
      ],
    },
  ],
}

describe('TopicTreePanel', () => {
  it('renders parent topics, child topics, and emits leaf document selection', async () => {
    const wrapper = mount(TopicTreePanel, {
      props: {
        tree: TREE,
        loading: false,
        rebuilding: false,
        selectedDocumentId: '',
        showRebuild: true,
      },
      global: { stubs: STUBS },
    })

    expect(wrapper.text()).toContain('财务治理')
    expect(wrapper.text()).not.toContain('年度审计')

    await wrapper.find('.topic-head').trigger('click')
    expect(wrapper.text()).toContain('年度审计')
    expect(wrapper.text()).not.toContain('audit-plan.pdf')

    await wrapper.find('.child-head').trigger('click')
    expect(wrapper.text()).toContain('audit-plan.pdf')

    await wrapper.find('.doc-name-chip').trigger('click')
    expect(wrapper.emitted('select-document')).toBeTruthy()
    expect(wrapper.emitted('select-document')[0]).toEqual(['doc-1', null])
  })
})
