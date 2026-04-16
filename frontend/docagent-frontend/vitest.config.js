import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import crypto from 'node:crypto'
import path from 'path'

if (!crypto.hash) {
  crypto.hash = (algorithm, data, outputEncoding = 'hex') =>
    crypto.createHash(algorithm).update(data).digest(outputEncoding)
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  test: {
    environment: 'jsdom',
    globals: true
  }
})
