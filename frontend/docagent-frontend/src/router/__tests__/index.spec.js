import { beforeEach, describe, expect, it } from 'vitest'

import { createAppRouter } from '@/router'
import { sessionStore } from '@/stores/session'

describe('router guards', () => {
  beforeEach(() => {
    sessionStore.clear()
  })

  it('redirects anonymous users to /login for protected pages', async () => {
    const router = createAppRouter()

    await router.push('/documents')
    await router.isReady()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/documents')
  })
})
