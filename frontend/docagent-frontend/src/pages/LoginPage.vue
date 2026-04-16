<template>
  <section class="login-page">
    <div class="login-hero">
      <p class="eyebrow">Enterprise Access</p>
      <h1>登录后进入企业文档工作台</h1>
      <p class="intro">
        当前阶段启用内部账号密码登录。登录成功后，页面导航、检索结果和文档访问都会按角色与部门范围自动收口。
      </p>
    </div>

    <form class="login-card" @submit.prevent="handleSubmit">
      <div class="card-head">
        <h2>账号登录</h2>
        <p>请输入管理员为你分配的企业账号。</p>
      </div>

      <label class="field">
        <span>用户名</span>
        <input
          v-model.trim="form.username"
          name="username"
          type="text"
          autocomplete="username"
          placeholder="例如：alice"
          required
        />
      </label>

      <label class="field">
        <span>密码</span>
        <input
          v-model="form.password"
          name="password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
          required
        />
      </label>

      <button class="submit-button" type="submit" :disabled="submitting">
        {{ submitting ? '登录中...' : '登录' }}
      </button>

      <p class="card-note">
        忘记密码请联系系统管理员。密码修改入口会在登录后开放。
      </p>
    </form>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api'
import { sessionStore } from '@/stores/session'

const router = useRouter()
const route = useRoute()

const submitting = ref(false)
const form = reactive({
  username: '',
  password: '',
})

async function handleSubmit() {
  if (submitting.value) {
    return
  }

  submitting.value = true
  try {
    const response = await api.login({
      username: form.username,
      password: form.password,
    })
    sessionStore.setSession(response.data || {})

    const redirectTarget =
      typeof route.query.redirect === 'string' && route.query.redirect
        ? route.query.redirect
        : '/'

    await router.replace(redirectTarget)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped lang="scss">
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(340px, 440px);
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.16), transparent 34%),
    linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
}

.login-hero {
  padding: 72px 56px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 18px;
}

.eyebrow {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #2563eb;
}

.login-hero h1 {
  max-width: 560px;
  font-size: 44px;
  line-height: 1.1;
  letter-spacing: -0.04em;
  color: #0f172a;
}

.intro {
  max-width: 540px;
  font-size: 16px;
  line-height: 1.8;
  color: #475569;
}

.login-card {
  margin: 28px;
  padding: 32px 30px;
  align-self: center;
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.94);
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.18);
}

.card-head h2 {
  font-size: 24px;
  font-weight: 700;
  color: #f8fafc;
}

.card-head p {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.7;
  color: #94a3b8;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field span {
  font-size: 12px;
  font-weight: 700;
  color: #cbd5e1;
}

.field input {
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.55);
  color: #f8fafc;
  padding: 13px 14px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.16s ease, background-color 0.16s ease;

  &::placeholder {
    color: #64748b;
  }

  &:focus {
    border-color: rgba(96, 165, 250, 0.8);
    background: rgba(15, 23, 42, 0.72);
  }
}

.submit-button {
  margin-top: 8px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
  color: #fff;
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;

  &:disabled {
    opacity: 0.72;
    cursor: wait;
  }
}

.card-note {
  font-size: 12px;
  line-height: 1.7;
  color: #94a3b8;
}

@media (max-width: 960px) {
  .login-page {
    grid-template-columns: 1fr;
  }

  .login-hero {
    padding: 48px 24px 12px;
  }

  .login-hero h1 {
    font-size: 34px;
  }

  .login-card {
    margin: 0 24px 32px;
  }
}
</style>
