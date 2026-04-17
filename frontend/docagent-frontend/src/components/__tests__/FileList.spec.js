import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import FileList from '@/components/FileList.vue'


vi.mock('@/api', () => ({
  api: {
    reclassifyDocument: vi.fn(),
    deleteDocument: vi.fn()
  }
}))

const STUBS = {
  ElTable: { template: '<div class="el-table-stub"><slot /></div>' },
  ElTableColumn: { template: '<div class="el-table-column-stub"></div>' },
  ElTag: { template: '<span class="el-tag-stub"><slot /></span>' },
  ElButton: { template: '<button><slot /></button>' },
  ElIcon: { template: '<span class="el-icon-stub"><slot /></span>' },
  Document: { template: '<span />' },
  Refresh: { template: '<span />' },
  RefreshRight: { template: '<span />' },
  Delete: { template: '<span />' }
}

function mountFileList() {
  return mount(FileList, {
    props: {
      documentList: [],
      loading: false
    },
    global: {
      stubs: STUBS,
      directives: {
        loading: () => {}
      }
    }
  })
}

describe('FileList', () => {
  it('formats classification_path as a breadcrumb when taxonomy metadata exists', () => {
    const wrapper = mountFileList()

    expect(
      wrapper.vm.getClassificationText({
        classification_result: 'Offer审批',
        classification_path: ['人力资源', '招聘管理', 'Offer审批']
      })
    ).toBe('人力资源 > 招聘管理 > Offer审批')
  })

  it('falls back to legacy classification_result when path is unavailable', () => {
    const wrapper = mountFileList()

    expect(
      wrapper.vm.getClassificationText({
        classification_result: '发票审批'
      })
    ).toBe('发票审批')
  })

  it('returns source badge labels for llm, keyword, and fallback states', () => {
    const wrapper = mountFileList()

    expect(wrapper.vm.getClassificationSourceMeta('llm')).toEqual({ label: 'AI', tone: 'ai' })
    expect(wrapper.vm.getClassificationSourceMeta('keyword')).toEqual({ label: '关键词', tone: 'keyword' })
    expect(wrapper.vm.getClassificationSourceMeta('fallback')).toEqual({ label: '待确认', tone: 'fallback' })
    expect(wrapper.vm.getClassificationText({})).toBe('未分类')
  })
})
