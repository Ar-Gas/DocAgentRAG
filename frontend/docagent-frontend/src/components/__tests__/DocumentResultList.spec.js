import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DocumentResultList from '@/components/DocumentResultList.vue'

const STUBS = {
  ElTag: { props: ['type', 'size'], template: '<span class="el-tag"><slot /></span>' },
  ElButton: { template: '<button><slot /></button>' },
  ElSkeleton: { template: '<div class="el-skeleton"></div>' },
  ElEmpty: { template: '<div class="el-empty"></div>' },
}

const DOC = {
  document_id: 'doc-1',
  filename: 'budget-report.pdf',
  file_type: '.pdf',
  classification_result: '财务制度',
  visibility_scope: 'department',
  business_category_name: '预算管理',
  owner_department_name: '财务部',
  score: 0.92,
  hit_count: 2,
  best_block_id: 'doc-1#2',
  best_excerpt: '预算审批流程和采购说明',
  matched_terms: ['预算', '审批'],
  evidence_blocks: [
    {
      block_id: 'doc-1#2',
      block_index: 2,
      block_type: 'paragraph',
      heading_path: ['第三章 财务管理'],
      page_number: 12,
      snippet: '预算审批流程和采购说明',
      score: 0.92,
    },
    {
      block_id: 'doc-1#5',
      block_index: 5,
      block_type: 'paragraph',
      heading_path: ['第三章 财务管理'],
      page_number: 12,
      snippet: '预算执行和报销约束',
      score: 0.81,
    },
  ],
}

describe('DocumentResultList', () => {
  it('shows filename in collapsed state; click header to expand evidence and emit select-document', async () => {
    const wrapper = mount(DocumentResultList, {
      props: { loading: false, query: '预算 审批', selectedDocumentId: '', documents: [DOC] },
      global: { stubs: STUBS },
    })

    // 默认折叠：能看到文件名，但看不到 mark（内容未展开）
    expect(wrapper.text()).toContain('budget-report.pdf')
    expect(wrapper.findAll('mark').length).toBe(0)

    // 点击 card-head 展开
    await wrapper.find('.card-head').trigger('click')

    // 展开后应看到 mark 高亮
    expect(wrapper.findAll('mark').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('第三章 财务管理')
    expect(wrapper.text()).toContain('第 12 页')
    expect(wrapper.text()).toContain('paragraph')

    // 并且发射了 select-document 事件
    expect(wrapper.emitted('select-document')).toBeTruthy()
    expect(wrapper.emitted('select-document')[0][0]).toBe('doc-1')
  })

  it('renders governed visibility and business badges in the collapsed card header', () => {
    const wrapper = mount(DocumentResultList, {
      props: { loading: false, query: '', selectedDocumentId: '', documents: [DOC] },
      global: { stubs: STUBS },
    })

    expect(wrapper.text()).toContain('部门文档')
    expect(wrapper.text()).toContain('预算管理')
    expect(wrapper.text()).toContain('财务部')
  })

  it('emits open-viewer when "原文预览" button is clicked', async () => {
    const wrapper = mount(DocumentResultList, {
      props: { loading: false, query: '', selectedDocumentId: 'doc-1', documents: [DOC] },
      global: { stubs: STUBS },
    })

    // 选中文档时自动展开（watch selectedDocumentId）
    await wrapper.vm.$nextTick()
    const viewerBtn = wrapper.findAll('.action-btn').find((b) => b.text().includes('原文预览'))
    expect(viewerBtn).toBeTruthy()
    await viewerBtn.trigger('click')
    expect(wrapper.emitted('open-viewer')).toBeTruthy()
    expect(wrapper.emitted('open-viewer')[0][0].document_id).toBe('doc-1')
  })
})
