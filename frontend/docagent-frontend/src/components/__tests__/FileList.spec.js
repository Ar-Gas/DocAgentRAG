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
    expect(wrapper.vm.getClassificationSourceMeta('llm_hierarchical')).toEqual({ label: 'AI', tone: 'ai' })
    expect(wrapper.vm.getClassificationSourceMeta('llm_hierarchical_fallback')).toBeNull()
    expect(wrapper.vm.getClassificationSourceMeta('keyword')).toEqual({ label: '关键词', tone: 'keyword' })
    expect(wrapper.vm.getClassificationSourceMeta('keyword_forced')).toEqual({ label: '模板分类', tone: 'keyword' })
    expect(wrapper.vm.getClassificationSourceMeta('fallback')).toBeNull()
    expect(wrapper.vm.getClassificationSourceMeta('domain_fallback')).toBeNull()
    expect(wrapper.vm.getClassificationSourceMeta('pending_sync')).toBeNull()
    expect(wrapper.vm.getClassificationSourceMeta('pending_local_content')).toEqual({ label: '待本地索引', tone: 'pending' })
    expect(wrapper.vm.getClassificationIssueMeta('no_match')).toEqual({ label: '待复核', tone: 'fallback' })
    expect(wrapper.vm.getClassificationText({})).toBe('未分类')
    expect(wrapper.vm.getClassificationText({ classification_issue_code: 'pending_local_content' })).toBe('待本地索引')
    expect(wrapper.vm.getClassificationText({ classification_issue_code: 'no_match' })).toBe('未分类')
  })

  it('shows taxonomy v3 paths as concrete classifications', () => {
    const wrapper = mountFileList()

    expect(
      wrapper.vm.getClassificationText({
        taxonomy_version: 'taxonomy_v3',
        classification_path: ['图书资料', '综合图书', '综合书籍'],
        classification_source: 'llm_hierarchical_fallback',
        classification_issue_code: null
      })
    ).toBe('图书资料 > 综合图书 > 综合书籍')

    expect(wrapper.vm.getClassificationText({ classification_issue_code: 'no_match' })).toBe('未分类')
  })

  it('does not render ingest or local index errors in classification details', () => {
    const wrapper = mountFileList()

    expect(
      wrapper.vm.getClassificationErrorDetails({
        local_index_status: 'ready',
        local_index_error: 'Unsupported file type: .xlsx',
        ingest_error: ''
      })
    ).toEqual([])

    expect(
      wrapper.vm.getClassificationErrorDetails({
        local_index_status: 'failed',
        local_index_error: 'parser failed',
        ingest_error: 'RetryError[x]'
      })
    ).toEqual([])

    expect(
      wrapper.vm.getClassificationErrorDetails({
        ingest_error: 'File content contains only whitespace characters'
      })
    ).toEqual([])
  })

  it('maps ingest statuses to visible tag metadata', () => {
    const wrapper = mountFileList()

    expect(wrapper.vm.getIngestStatusMeta('queued')).toEqual({ label: '待导入', tone: 'info' })
    expect(wrapper.vm.getIngestStatusMeta('processing')).toEqual({ label: '导入中', tone: 'warning' })
    expect(wrapper.vm.getIngestStatusMeta('ready')).toEqual({ label: '已入库', tone: 'success' })
    expect(wrapper.vm.getIngestStatusMeta('failed')).toEqual({ label: '失败', tone: 'danger' })
    expect(wrapper.vm.getIngestStatusMeta('local_only')).toEqual({ label: '待导入', tone: 'info' })
    expect(wrapper.vm.getIngestStatusMeta('')).toEqual({ label: '未知', tone: 'info' })
    expect(wrapper.vm.getIngestStatusMeta('', { file_available: true })).toEqual({ label: '本地可用', tone: 'info' })
    expect(
      wrapper.vm.getIngestStatusMeta('queued', { local_index_status: 'ready', file_type: '.pdf' })
    ).toEqual({ label: '本地可用', tone: 'info' })
    expect(
      wrapper.vm.getIngestStatusMeta('processing', { local_index_status: 'ready', file_type: '.pdf' })
    ).toEqual({ label: '本地可用', tone: 'info' })
    expect(
      wrapper.vm.getIngestStatusMeta('local_only', { local_index_status: 'ready', file_type: '.png' })
    ).toEqual({ label: '本地可用', tone: 'info' })
    expect(
      wrapper.vm.getIngestStatusMeta('local_only', {
        local_index_status: 'ready',
        file_type: '.pdf',
        ingest_error: 'File content contains only whitespace characters'
      })
    ).toEqual({ label: '本地可用', tone: 'info' })
  })

  it('maps local index statuses to visible tag metadata', () => {
    const wrapper = mountFileList()

    expect(wrapper.vm.getLocalIndexStatusMeta('queued')).toEqual({ label: '待索引', tone: 'info' })
    expect(wrapper.vm.getLocalIndexStatusMeta('processing')).toEqual({ label: '索引中', tone: 'warning' })
    expect(wrapper.vm.getLocalIndexStatusMeta('ready')).toEqual({ label: '可浏览', tone: 'success' })
    expect(wrapper.vm.getLocalIndexStatusMeta('failed')).toEqual({ label: '失败', tone: 'danger' })
    expect(wrapper.vm.getLocalIndexStatusMeta('')).toEqual({ label: '未知', tone: 'info' })
    expect(wrapper.vm.getLocalIndexStatusMeta('', { preview_content: '正文' })).toEqual({ label: '可浏览', tone: 'success' })
  })

  it('prefers storage_path when rendering file storage location', () => {
    const wrapper = mountFileList()

    expect(
      wrapper.vm.getStoragePathText({
        storage_path: 'classified_docs/图书资料/经济金融图书/金融历史书籍/finance-history.pdf',
        filepath: '/abs/path/finance-history.pdf'
      })
    ).toBe('classified_docs/图书资料/经济金融图书/金融历史书籍/finance-history.pdf')

    expect(
      wrapper.vm.getStoragePathText({
        filepath: '/abs/path/finance-history.pdf'
      })
    ).toBe('/abs/path/finance-history.pdf')
  })
})
