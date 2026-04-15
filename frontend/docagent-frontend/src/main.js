import { createApp } from 'vue'
import App from './App.vue'
import {
  ElButton,
  ElDatePicker,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElOption,
  ElSelect,
  ElSkeleton,
  ElSlider,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElUpload,
  vLoading,
} from 'element-plus'
import 'element-plus/dist/index.css'
import '@/assets/styles/global.scss'

import { createAppRouter } from '@/router'
import { sessionStore } from '@/stores/session'

sessionStore.hydrate()

const router = createAppRouter()
const app = createApp(App)

;[
  ElButton,
  ElDatePicker,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElOption,
  ElSelect,
  ElSkeleton,
  ElSlider,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElUpload,
].forEach((component) => {
  app.component(component.name, component)
})

app.directive('loading', vLoading)
app.use(router)
app.mount('#app')
