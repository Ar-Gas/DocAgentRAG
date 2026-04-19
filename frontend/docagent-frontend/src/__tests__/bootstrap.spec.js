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

  it('index html avoids vite default branding', () => {
    const indexPath = path.resolve(currentDir, '../../index.html')
    const source = fs.readFileSync(indexPath, 'utf8')

    expect(source).not.toContain('/vite.svg')
    expect(source).toContain('<title>DocAgent</title>')
  })
})
