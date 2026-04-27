// @vitest-environment node

import { describe, expect, it } from 'vitest'

import viteConfig from '../vite.config.js'

const manualChunks = viteConfig.build?.rollupOptions?.output?.manualChunks

describe('vite manualChunks', () => {
  it('keeps Vue runtime and router in the same vendor chunk', () => {
    expect(manualChunks).toBeTypeOf('function')
    expect(manualChunks('/node_modules/vue/dist/vue.runtime.esm-bundler.js')).toBe('vendor')
    expect(manualChunks('/node_modules/vue-router/dist/vue-router.mjs')).toBe('vendor')
  })

  it('still splits element-plus and axios into dedicated chunks', () => {
    expect(manualChunks('/node_modules/element-plus/es/index.mjs')).toBe('element-plus')
    expect(manualChunks('/node_modules/axios/index.js')).toBe('http-vendor')
  })
})
