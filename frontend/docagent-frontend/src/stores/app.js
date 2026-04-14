/**
 * 全局应用状态（轻量版，不依赖 Pinia）
 *
 * 用法：
 *   import { appStore } from '@/stores/app'
 *   appStore.startLoading('正在重建主题树...')
 *   appStore.stopLoading()
 */
import { reactive } from 'vue'

export const appStore = reactive({
  globalLoading: false,
  loadingMessage: '',

  startLoading(msg = '处理中...') {
    this.globalLoading = true
    this.loadingMessage = msg
  },

  stopLoading() {
    this.globalLoading = false
    this.loadingMessage = ''
  },
})
