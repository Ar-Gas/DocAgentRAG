import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import DocumentViewerModal from '@/components/DocumentViewerModal.vue'

const apiMocks = vi.hoisted(() => ({
  getDocumentFileBlob: vi.fn(() => Promise.resolve(new Blob(['file']))),
  getDocumentReader: vi.fn()
}))

vi.mock('@/api', () => ({
  api: {
    getDocumentFileBlob: apiMocks.getDocumentFileBlob,
    getDocumentReader: apiMocks.getDocumentReader
  }
}))

const STUBS = {
  ElDialog: {
    props: ['modelValue', 'title', 'fullscreen', 'destroyOnClose'],
    template: `
      <div class="el-dialog-stub">
        <div class="dialog-header"><slot name="header" /></div>
        <div class="dialog-body"><slot /></div>
      </div>
    `
  },
  ElTag: { template: '<span class="el-tag"><slot /></span>' },
  ElButton: {
    props: ['disabled'],
    template: '<button :disabled="disabled"><slot /></button>'
  },
  ElSkeleton: { template: '<div class="el-skeleton"></div>' },
  ElEmpty: { props: ['description'], template: '<div class="el-empty">{{ description }}</div>' },
  VueOfficePdf: {
    name: 'VueOfficePdf',
    props: ['src'],
    template: '<div class="pdf-renderer-stub" :data-src="src">pdf renderer</div>'
  },
  VueOfficeDocx: {
    name: 'VueOfficeDocx',
    props: ['src'],
    template: '<div class="docx-renderer-stub" :data-src="src">docx renderer</div>'
  },
  VueOfficeExcel: {
    name: 'VueOfficeExcel',
    props: ['src'],
    template: '<div class="excel-renderer-stub" :data-src="src">excel renderer</div>'
  }
}

describe('DocumentViewerModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    URL.createObjectURL = vi.fn(() => 'blob:docagent-preview')
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders pdf files with the dedicated pdf viewer branch instead of native iframe', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-1',
        filename: 'budget-report.pdf',
        fileType: '.pdf'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.find('.pdf-renderer-stub').exists()).toBe(true)
    expect(wrapper.find('iframe.native-iframe').exists()).toBe(false)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('shows a friendly empty state when the original file is unavailable', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-2',
        filename: 'missing.pdf',
        fileType: '.pdf',
        fileAvailable: false
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.text()).toContain('原文件不存在')
    expect(wrapper.find('.pdf-renderer-stub').exists()).toBe(false)
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('renders docx files with the docx office viewer', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-3',
        filename: 'report.docx',
        fileType: '.docx'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.find('.docx-renderer-stub').exists()).toBe(true)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('renders xlsx files with the excel office viewer', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-4',
        filename: 'budget.xlsx',
        fileType: '.xlsx'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.find('.excel-renderer-stub').exists()).toBe(true)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('shows unsupported state for pptx files instead of extracted text', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-5',
        filename: 'slides.pptx',
        fileType: '.pptx'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.text()).toContain('暂不支持在线预览')
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('shows unsupported state for txt files instead of extracted text', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-6',
        filename: 'notes.txt',
        fileType: '.txt'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.text()).toContain('暂不支持在线预览')
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('shows the missing-file state even for docx files', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-7',
        filename: 'missing.docx',
        fileType: '.docx',
        fileAvailable: false
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.text()).toContain('原文件不存在')
    expect(wrapper.find('.docx-renderer-stub').exists()).toBe(false)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('normalizes extension-like fileType values before routing', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-8',
        filename: 'report.DOCX',
        fileType: 'DOCX'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.find('.docx-renderer-stub').exists()).toBe(true)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('falls back to the filename extension when fileType is missing', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-9',
        filename: 'fallback.xlsx',
        fileType: ''
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.find('.excel-renderer-stub').exists()).toBe(true)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('falls back to the filename extension when fileType is a mime type', () => {
    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-10',
        filename: 'mime-fallback.pdf',
        fileType: 'application/pdf'
      },
      global: {
        stubs: STUBS
      }
    })

    expect(wrapper.find('.pdf-renderer-stub').exists()).toBe(true)
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })

  it('shows a timeout fallback if the office renderer never finishes', async () => {
    vi.useFakeTimers()

    const wrapper = mount(DocumentViewerModal, {
      props: {
        visible: true,
        documentId: 'doc-11',
        filename: 'slow.pdf',
        fileType: '.pdf'
      },
      global: {
        stubs: STUBS
      }
    })

    await vi.advanceTimersByTimeAsync(15000)

    expect(wrapper.text()).toContain('预览加载超时')
    expect(apiMocks.getDocumentReader).not.toHaveBeenCalled()
  })
})
