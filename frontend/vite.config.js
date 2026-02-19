import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 3000,
    proxy: {
      // 代理API请求到后端，解决跨域
      '/api': {
        target: 'http://localhost:6008', // 你的FastAPI后端地址
        changeOrigin: true,
        rewrite: (path) => path
      }
    }
  }
})
