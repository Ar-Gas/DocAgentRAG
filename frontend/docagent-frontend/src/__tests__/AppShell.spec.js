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

    const navItems = wrapper.findAll('.nav-link').map((link) => link.text())

    expect(wrapper.find('.page-title').text()).toBe('全局目录')
    expect(wrapper.find('.page-subtitle').text()).toBe(
      '以权限目录为主线，统一收口全局目录、具体检索、台账与管理后台。',
    )
    expect(navItems).toEqual(
      expect.arrayContaining(['全局目录', '具体检索', '上传文档', '文档台账']),
    )
    expect(navItems).not.toContain('工作台')
    expect(navItems).not.toContain('用户管理')
    expect(navItems).not.toContain('审计日志')
  })
})
