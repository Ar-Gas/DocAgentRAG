import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import App from '@/App.vue'
import { createAppRouter } from '@/router'
import { sessionStore } from '@/stores/session'

describe('App shell', () => {
  beforeEach(() => {
    sessionStore.clear()
  })

  it('shows only employee navigation for employee role', async () => {
    sessionStore.setSession({
      token: 'token-1',
      user: {
        username: 'alice',
        display_name: 'Alice',
        role_code: 'employee',
      },
    })

    const router = createAppRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
        stubs: {
          ElIcon: true,
          RouterView: { template: '<div />' },
        },
      },
    })

    expect(wrapper.text()).toContain('工作台')
    expect(wrapper.text()).toContain('上传文档')
    expect(wrapper.text()).not.toContain('用户管理')
    expect(wrapper.text()).not.toContain('审计日志')
  })
})
