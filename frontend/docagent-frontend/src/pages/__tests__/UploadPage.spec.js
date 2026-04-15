import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { sessionStore } from '@/stores/session'

const apiMocks = vi.hoisted(() => ({
  getDepartments: vi.fn(),
  getSystemCategories: vi.fn(),
  getDepartmentCategories: vi.fn(),
}))

vi.mock('@/api', () => ({
  api: apiMocks,
}))

describe('UploadPage', () => {
  beforeEach(() => {
    apiMocks.getDepartments.mockResolvedValue({
      data: [
        { id: 'dept-fin', name: '财务部' },
        { id: 'dept-ops', name: '运营部' },
        { id: 'dept-legal', name: '法务部' },
      ],
    })
    apiMocks.getSystemCategories.mockResolvedValue({
      data: [{ id: 'cat-policy', name: '制度流程' }],
    })
    apiMocks.getDepartmentCategories.mockResolvedValue({
      data: [{ id: 'cat-budget', name: '预算管理' }],
    })
  })

  afterEach(() => {
    sessionStore.clear()
    vi.clearAllMocks()
  })

  it('limits upload department options to the employee primary and collaborative departments', async () => {
    sessionStore.setSession({
      token: 'token-1',
      user: {
        role_code: 'employee',
        primary_department_id: 'dept-fin',
        collaborative_department_ids: ['dept-ops'],
      },
    })

    const UploadPage = (await import('@/pages/UploadPage.vue')).default
    const wrapper = mount(UploadPage, {
      global: {
        stubs: {
          FileUpload: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.vm.allowedDepartmentIds).toContain('dept-fin')
    expect(wrapper.vm.allowedDepartmentIds).toContain('dept-ops')
    expect(wrapper.vm.allowedDepartmentIds).not.toContain('dept-legal')
  })
})
