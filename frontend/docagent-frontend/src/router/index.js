import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/pages/DashboardPage.vue')
  },
  {
    path: '/documents',
    name: 'documents',
    component: () => import('@/pages/DocumentsPage.vue')
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('@/pages/SearchPage.vue')
  },
  {
    path: '/qa',
    name: 'qa',
    component: () => import('@/pages/QAPage.vue')
  },
  {
    path: '/graph',
    name: 'graph',
    component: () => import('@/pages/GraphPage.vue')
  },
  {
    path: '/rag-studio',
    name: 'rag-studio',
    component: () => import('@/pages/RagStudioPage.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
