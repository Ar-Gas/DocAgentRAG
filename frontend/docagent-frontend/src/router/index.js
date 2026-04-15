import { h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import { canAccessRoles, sessionStore } from '@/stores/session'

function createPlaceholderPage(title, description) {
  return {
    name: `${title}Placeholder`,
    render() {
      return h('section', { class: 'route-placeholder' }, [
        h('div', { class: 'route-placeholder__card' }, [
          h('h2', title),
          h('p', description),
        ]),
      ])
    },
  }
}

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: {
      public: true,
      hideInNav: true,
      hideInShell: true,
      title: '登录',
    },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/pages/DashboardPage.vue'),
    meta: {
      requiresAuth: true,
      navLabel: '工作台',
      title: '工作台',
      navOrder: 10,
    },
  },
  {
    path: '/documents',
    name: 'documents',
    component: () => import('@/pages/DocumentsPage.vue'),
    meta: {
      requiresAuth: true,
      navLabel: '上传文档',
      title: '文档管理',
      navOrder: 20,
    },
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('@/pages/SearchPage.vue'),
    meta: {
      requiresAuth: true,
      navLabel: '智能检索',
      title: '智能检索',
      navOrder: 30,
    },
  },
  {
    path: '/taxonomy',
    name: 'taxonomy',
    component: () => import('@/pages/TaxonomyPage.vue'),
    meta: {
      requiresAuth: true,
      hideInNav: true,
      title: '语义主题树',
    },
  },
  {
    path: '/admin/users',
    name: 'user-admin',
    component: createPlaceholderPage('用户管理', '用户、部门和角色管理页会在后续任务中接入。'),
    meta: {
      requiresAuth: true,
      roles: ['system_admin'],
      navLabel: '用户管理',
      title: '用户管理',
      navOrder: 40,
    },
  },
  {
    path: '/admin/audit',
    name: 'audit-log',
    component: createPlaceholderPage('审计日志', '审计日志界面会在后续任务中接入。'),
    meta: {
      requiresAuth: true,
      roles: ['system_admin', 'audit_readonly'],
      navLabel: '审计日志',
      title: '审计日志',
      navOrder: 50,
    },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
    meta: {
      hideInNav: true,
      hideInShell: true,
    },
  },
]

export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes,
  })

  router.beforeEach((to) => {
    if (to.meta.public) {
      if (to.path === '/login' && sessionStore.isAuthenticated.value) {
        const redirectTarget = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
        return redirectTarget
      }
      return true
    }

    if (!sessionStore.isAuthenticated.value) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }

    if (!canAccessRoles(to.meta.roles || [])) {
      return { path: '/' }
    }

    return true
  })

  return router
}

export { routes }

export default createAppRouter()
