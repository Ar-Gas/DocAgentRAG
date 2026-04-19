import { describe, expect, it } from 'vitest'

import router from '@/router'

describe('router', () => {
  it('registers qa, graph, and rag studio routes', () => {
    const routeNames = router.getRoutes().map((route) => route.name)

    expect(routeNames).toContain('qa')
    expect(routeNames).toContain('graph')
    expect(routeNames).toContain('rag-studio')
  })
})
