<template>
  <div class="app-shell">
    <aside class="shell-sidebar">
      <!-- Logo -->
      <div class="sidebar-brand">
        <div class="brand-icon">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <rect x="2" y="2" width="7" height="9" rx="1.5" fill="currentColor" opacity="0.9"/>
            <rect x="11" y="2" width="7" height="5" rx="1.5" fill="currentColor" opacity="0.6"/>
            <rect x="11" y="9" width="7" height="9" rx="1.5" fill="currentColor" opacity="0.75"/>
            <rect x="2" y="13" width="7" height="5" rx="1.5" fill="currentColor" opacity="0.5"/>
          </svg>
        </div>
        <div class="brand-text">
          <span class="brand-name">DocAgent</span>
          <span class="brand-sub">智能文档工作台</span>
        </div>
      </div>

      <!-- 导航 -->
      <nav class="sidebar-nav">
        <span class="nav-section-label">工作区</span>
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-link">
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <!-- 底部状态 -->
      <div class="sidebar-footer">
        <div class="system-status">
          <span class="status-dot"></span>
          <span>系统运行中</span>
        </div>
        <p class="footer-note">FastAPI · Vue 3 · ChromaDB</p>
      </div>
    </aside>

    <div class="shell-body">
      <header class="shell-topbar">
        <div class="topbar-left">
          <h1 class="page-title">{{ currentPageTitle }}</h1>
        </div>
        <div class="topbar-right">
          <span class="topbar-badge">AI 驱动 · 本地向量检索</span>
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
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { DataBoard, Document, Search, ChatDotRound, Share } from '@element-plus/icons-vue'

const navItems = [
  { to: '/',          label: '总览',     icon: DataBoard },
  { to: '/documents', label: '文档管理', icon: Document  },
  { to: '/search',    label: '智能检索', icon: Search    },
  { to: '/qa',        label: '智能问答', icon: ChatDotRound },
  { to: '/graph',     label: '知识图谱', icon: Share },
]

const route = useRoute()
const pageTitleMap = {
  '/': '总览',
  '/documents': '文档管理',
  '/search': '智能检索',
  '/qa': '智能问答',
  '/graph': '知识图谱',
}
const currentPageTitle = computed(() => pageTitleMap[route.path] || 'DocAgent')
</script>

<style scoped lang="scss">
.app-shell {
  display: flex;
  min-height: 100vh;
}

/* ── 侧边栏 ── */
.shell-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #0F172A;
  display: flex;
  flex-direction: column;
  padding: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.brand-icon {
  width: 36px;
  height: 36px;
  background: var(--blue-600);
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: #fff;
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-name {
  font-size: 15px;
  font-weight: 700;
  color: #F8FAFC;
  letter-spacing: -0.01em;
}

.brand-sub {
  font-size: 11px;
  color: #64748B;
  margin-top: 1px;
}

/* ── 导航 ── */
.sidebar-nav {
  flex: 1;
  padding: 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #475569;
  padding: 0 8px;
  margin-bottom: 6px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 7px;
  color: #94A3B8;
  font-size: 13.5px;
  font-weight: 500;
  transition: background 0.12s, color 0.12s;
  text-decoration: none;

  .nav-icon { font-size: 16px; flex-shrink: 0; }

  &:hover {
    background: rgba(255,255,255,0.06);
    color: #CBD5E1;
  }

  &.router-link-active {
    background: rgba(37, 99, 235, 0.2);
    color: #93C5FD;

    .nav-icon { color: #60A5FA; }
  }
}

/* ── 底部 ── */
.sidebar-footer {
  padding: 14px 16px;
  border-top: 1px solid rgba(255,255,255,0.06);
}

.system-status {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: #64748B;
  margin-bottom: 4px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22C55E;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.25);
  flex-shrink: 0;
}

.footer-note {
  font-size: 11px;
  color: #334155;
}

/* ── 主体 ── */
.shell-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ── 顶栏 ── */
.shell-topbar {
  height: 52px;
  background: #fff;
  border-bottom: 1px solid var(--line);
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 100;
}

.page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-strong);
  letter-spacing: -0.01em;
}

.topbar-badge {
  font-size: 11px;
  font-weight: 500;
  color: var(--ink-muted);
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  padding: 3px 10px;
  border-radius: 999px;
}

/* ── 内容区 ── */
.shell-content {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
}

/* ── 响应式 ── */
@media (max-width: 1024px) {
  .shell-sidebar { width: 60px; }
  .brand-text, .nav-link span, .nav-section-label,
  .sidebar-footer .system-status span, .footer-note { display: none; }
  .sidebar-brand { justify-content: center; padding: 16px 0; }
  .sidebar-nav { align-items: center; }
  .nav-link { justify-content: center; padding: 10px; }
  .sidebar-footer { display: flex; justify-content: center; }
  .system-status { margin: 0; }
}
</style>
