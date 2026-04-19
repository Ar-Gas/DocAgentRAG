import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import FileList from '@/components/FileList.vue'


vi.mock('@/api', () => ({
  api: {
    reclassifyDocument: vi.fn(),
    deleteDocument: vi.fn(),
    retryDocumentIngest: vi.fn()
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

  it('returns source badge labels for classification states', () => {
    const wrapper = mountFileList()

    expect(wrapper.vm.getClassificationSourceMeta('llm')).toEqual({ label: 'AI', tone: 'ai' })
    expect(wrapper.vm.getClassificationSourceMeta('llm_forced')).toEqual({ label: 'AI', tone: 'ai' })
    expect(wrapper.vm.getClassificationSourceMeta('keyword')).toEqual({ label: '关键词', tone: 'keyword' })
    expect(wrapper.vm.getClassificationSourceMeta('keyword_forced')).toEqual({ label: '模板分类', tone: 'keyword' })
    expect(wrapper.vm.getClassificationSourceMeta('fallback')).toEqual({ label: '待确认', tone: 'fallback' })
    expect(wrapper.vm.getClassificationSourceMeta('pending_sync')).toEqual({ label: '待同步', tone: 'pending' })
    expect(wrapper.vm.getClassificationText({})).toBe('未分类')
  })

  it('maps ingest statuses to visible tag metadata', () => {
    const wrapper = mountFileList()

    expect(wrapper.vm.getIngestStatusMeta('queued')).toEqual({ label: '待导入', tone: 'info' })
    expect(wrapper.vm.getIngestStatusMeta('processing')).toEqual({ label: '导入中', tone: 'warning' })
    expect(wrapper.vm.getIngestStatusMeta('ready')).toEqual({ label: '已入库', tone: 'success' })
    expect(wrapper.vm.getIngestStatusMeta('failed')).toEqual({ label: '失败', tone: 'danger' })
    expect(wrapper.vm.getIngestStatusMeta('local_only')).toEqual({ label: '待导入', tone: 'info' })
    expect(wrapper.vm.getIngestStatusMeta('')).toEqual({ label: '未知', tone: 'info' })
  })
})
