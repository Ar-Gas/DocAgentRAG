<template>
  <RouterView v-if="route.meta.public" />

  <div v-else class="app-shell">
    <aside class="shell-sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="2" y="2" width="7" height="9" rx="1.5" fill="currentColor" opacity="0.9" />
            <rect x="11" y="2" width="7" height="5" rx="1.5" fill="currentColor" opacity="0.6" />
            <rect x="11" y="9" width="7" height="9" rx="1.5" fill="currentColor" opacity="0.75" />
            <rect x="2" y="13" width="7" height="5" rx="1.5" fill="currentColor" opacity="0.5" />
          </svg>
        </div>
        <div class="brand-text">
          <span class="brand-name">DocAgent</span>
          <span class="brand-sub">企业文档工作台</span>
        </div>
      </div>

      <nav class="sidebar-nav">
        <span class="nav-section-label">工作区</span>
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="item.path"
          class="nav-link"
        >
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="system-status">
          <span class="status-dot"></span>
          <span>认证会话已连接</span>
        </div>
        <p class="footer-note">{{ sessionStore.roleLabel.value }}</p>
      </div>
    </aside>

    <div class="shell-body">
      <header class="shell-topbar">
        <div class="topbar-left">
          <h1 class="page-title">{{ currentPageTitle }}</h1>
          <p class="page-subtitle">按角色展示导航并统一收口登录态。</p>
        </div>
        <div class="topbar-right">
          <div class="user-chip">
            <span class="user-name">{{ sessionStore.displayName.value || '未命名用户' }}</span>
            <span class="user-role">{{ sessionStore.roleLabel.value }}</span>
          </div>
          <button type="button" class="logout-button" @click="handleLogout">
            退出登录
          </button>
        </div>
      </header>

      <main class="shell-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { DataBoard, Document, Search, UserFilled, Notebook } from '@element-plus/icons-vue'

import { api } from '@/api'
import { canAccessRoles, sessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()

const iconByRouteName = {
  dashboard: DataBoard,
  documents: Document,
  search: Search,
  'user-admin': UserFilled,
  'audit-log': Notebook,
}

const navItems = computed(() =>
  router
    .getRoutes()
    .filter((record) => {
      if (record.meta?.hideInNav || !record.meta?.navLabel) {
        return false
      }
      return canAccessRoles(record.meta.roles || [])
    })
    .sort((left, right) => (left.meta?.navOrder || 999) - (right.meta?.navOrder || 999))
    .map((record) => ({
      name: record.name,
      path: record.path,
      label: record.meta?.navLabel,
      icon: iconByRouteName[record.name] || Document,
    })),
)

const currentPageTitle = computed(
  () => route.meta?.title || route.meta?.navLabel || 'DocAgent',
)

async function handleLogout() {
  try {
    await api.logout()
  } catch (_error) {
    // Ignore logout API errors and clear local session anyway.
  } finally {
    sessionStore.clear()
    await router.replace('/login')
  }
}
</script>

<style scoped lang="scss">
.app-shell {
  display: flex;
  min-height: 100vh;
}

.shell-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: #0f172a;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 18px 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #fff;
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-name {
  font-size: 15px;
  font-weight: 700;
  color: #f8fafc;
}

.brand-sub {
  margin-top: 2px;
  font-size: 11px;
  color: #94a3b8;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 18px 12px;
}

.nav-section-label {
  padding: 0 10px 8px;
  font-size: 10px;
  font-weight: 700;
  color: #475569;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  color: #94a3b8;
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: background-color 0.16s ease, color 0.16s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.08);
    color: #e2e8f0;
  }

  &.router-link-active {
    background: rgba(37, 99, 235, 0.22);
    color: #bfdbfe;
  }
}

.nav-icon {
  font-size: 16px;
}

.sidebar-footer {
  padding: 16px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.system-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #cbd5e1;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
}

.footer-note {
  margin-top: 6px;
  font-size: 11px;
  color: #64748b;
}

.shell-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.shell-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(14px);
}

.topbar-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ink-strong);
}

.page-subtitle {
  font-size: 12px;
  color: var(--ink-muted);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.user-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink-strong);
}

.user-role {
  font-size: 11px;
  color: var(--ink-muted);
}

.logout-button {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink-strong);
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;

  &:hover {
    background: var(--bg-subtle);
  }
}

.shell-content {
  flex: 1;
  padding: 22px 24px;
  overflow-y: auto;
}

@media (max-width: 1024px) {
  .shell-sidebar {
    width: 76px;
  }

  .brand-text,
  .nav-link span,
  .nav-section-label,
  .footer-note,
  .system-status span {
    display: none;
  }

  .sidebar-brand,
  .sidebar-footer {
    justify-content: center;
  }

  .sidebar-nav {
    align-items: center;
  }

  .nav-link {
    justify-content: center;
  }
}

@media (max-width: 768px) {
  .app-shell {
    flex-direction: column;
  }

  .shell-sidebar {
    width: 100%;
    height: auto;
    position: static;
  }

  .shell-topbar,
  .shell-content {
    padding-left: 16px;
    padding-right: 16px;
  }

  .topbar-right {
    align-items: flex-end;
    flex-direction: column;
  }
}
</style>
