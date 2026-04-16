import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { sessionStore } from '@/stores/session'

const apiMocks = vi.hoisted(() => ({
  getUsers: vi.fn(),
  getDepartments: vi.fn(),
  getRoles: vi.fn(),
}))

vi.mock('@/api', () => ({
  api: apiMocks,
}))

describe('UserAdminPage', () => {
  beforeEach(() => {
    apiMocks.getUsers.mockResolvedValue({
      data: {
        items: [
          {
            id: 'user-1',
            username: 'alice',
            display_name: 'Alice',
            role_code: 'employee',
            primary_department_id: 'dept-fin',
          },
        ],
        total: 1,
      },
    })
    apiMocks.getDepartments.mockResolvedValue({
      data: [{ id: 'dept-fin', name: '财务部' }],
    })
    apiMocks.getRoles.mockResolvedValue({
      data: [{ code: 'employee', name: '普通员工' }],
    })
  })

  afterEach(() => {
    sessionStore.clear()
    vi.clearAllMocks()
  })

  it('loads user and department data for system admins', async () => {
    sessionStore.setSession({
      token: 'token-1',
      user: { role_code: 'system_admin', username: 'admin' },
    })

    const UserAdminPage = (await import('@/pages/UserAdminPage.vue')).default
    const wrapper = mount(UserAdminPage)
    await flushPromises()

    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('财务部')
  })
})
