import { computed, reactive } from 'vue'

const STORAGE_KEY = 'docagent-session'

const ROLE_LABELS = {
  system_admin: '系统管理员',
  department_admin: '部门管理员',
  employee: '员工',
  audit_readonly: '审计只读',
}

const state = reactive({
  token: '',
  user: null,
})

function persist() {
  if (typeof window === 'undefined') {
    return
  }

  if (!state.token || !state.user) {
    window.localStorage.removeItem(STORAGE_KEY)
    return
  }

  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      token: state.token,
      user: state.user,
    }),
  )
}

export const sessionStore = {
  state,
  isAuthenticated: computed(() => Boolean(state.token && state.user)),
  roleCode: computed(() => state.user?.role_code || ''),
  roleLabel: computed(() => ROLE_LABELS[state.user?.role_code] || '未认证'),
  displayName: computed(() => state.user?.display_name || state.user?.username || ''),
  hydrate() {
    if (typeof window === 'undefined') {
      return
    }

    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return
    }

    try {
      const parsed = JSON.parse(raw)
      state.token = parsed.token || ''
      state.user = parsed.user || null
    } catch (_error) {
      this.clear()
    }
  },
  setSession(payload = {}) {
    state.token = payload.token || ''
    state.user = payload.user || null
    persist()
  },
  updateUser(user) {
    state.user = user || null
    persist()
  },
  clear() {
    state.token = ''
    state.user = null

    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  },
}

export function canAccessRoles(roles = []) {
  if (!roles.length) {
    return true
  }
  return roles.includes(sessionStore.roleCode.value)
}
