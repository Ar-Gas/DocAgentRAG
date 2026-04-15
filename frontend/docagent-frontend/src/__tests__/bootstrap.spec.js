import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const mainEntryPath = path.resolve(currentDir, '../main.js')

describe('frontend bootstrap entry', () => {
  it('avoids full Element Plus and icon-bundle registration', () => {
    const source = fs.readFileSync(mainEntryPath, 'utf8')

    expect(source).not.toMatch(/import\s+ElementPlus\s+from\s+['"]element-plus['"]/)
    expect(source).not.toMatch(/app\.use\(ElementPlus\)/)
    expect(source).not.toMatch(/\*\s+as\s+ElementPlusIconsVue/)
  })

  it('rehydrates and revalidates persisted sessions before mounting', () => {
    const source = fs.readFileSync(mainEntryPath, 'utf8')

    expect(source).toContain('sessionStore.hydrate()')
    expect(source).toContain('api.getCurrentUser()')
  })
})
