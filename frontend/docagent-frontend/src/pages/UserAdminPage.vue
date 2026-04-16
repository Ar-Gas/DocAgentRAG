<template>
  <section class="admin-page">
    <div class="page-header shell-panel">
      <div>
        <h3>用户管理</h3>
        <p>系统管理员统一查看账号、主协作部门与角色分配，并在需要时快速新增企业账号。</p>
      </div>
      <button type="button" class="ghost-button" :disabled="loading" @click="loadData">
        {{ loading ? '加载中…' : '刷新数据' }}
      </button>
    </div>

    <div class="admin-grid">
      <article class="shell-panel panel-stack">
        <div class="panel-head">
          <div>
            <h4>账号台账</h4>
            <p>共 {{ users.length }} 个账号</p>
          </div>
        </div>

        <div v-if="loading" class="empty-copy">正在加载用户信息…</div>

        <div v-else-if="users.length" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>用户名</th>
                <th>显示名</th>
                <th>角色</th>
                <th>主部门</th>
                <th>协作部门</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in users" :key="user.id">
                <td>{{ user.username }}</td>
                <td>{{ user.display_name || '-' }}</td>
                <td>{{ roleNameByCode[user.role_code] || user.role_code }}</td>
                <td>{{ departmentNameById[user.primary_department_id] || user.primary_department_id || '-' }}</td>
                <td>{{ formatCollaborativeDepartments(user.collaborative_department_ids) }}</td>
                <td>{{ user.status === 'enabled' ? '启用' : '停用' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else class="empty-copy">当前没有可展示的用户数据。</div>
      </article>

      <article class="shell-panel panel-stack">
        <div class="panel-head">
          <div>
            <h4>新增账号</h4>
            <p>基于系统角色和部门归属创建新用户。</p>
          </div>
        </div>

        <form class="form-grid" @submit.prevent="handleCreateUser">
          <label>
            <span>用户名</span>
            <input v-model.trim="createForm.username" type="text" placeholder="例如 alice" />
          </label>
          <label>
            <span>显示名</span>
            <input v-model.trim="createForm.display_name" type="text" placeholder="例如 Alice" />
          </label>
          <label>
            <span>初始密码</span>
            <input v-model="createForm.password" type="password" placeholder="输入初始密码" />
          </label>
          <label>
            <span>角色</span>
            <select v-model="createForm.role_code">
              <option value="">请选择角色</option>
              <option v-for="role in roles" :key="role.code" :value="role.code">
                {{ role.name || role.code }}
              </option>
            </select>
          </label>
          <label>
            <span>主部门</span>
            <select v-model="createForm.primary_department_id">
              <option value="">请选择部门</option>
              <option v-for="department in departments" :key="department.id" :value="department.id">
                {{ department.name }}
              </option>
            </select>
          </label>
          <label>
            <span>协作部门</span>
            <input
              v-model.trim="createForm.collaborative_departments_text"
              type="text"
              placeholder="用逗号分隔多个部门 ID"
            />
          </label>
        </form>

        <div class="panel-actions">
          <button type="button" class="primary-button" :disabled="submitting" @click="handleCreateUser">
            {{ submitting ? '提交中…' : '创建用户' }}
          </button>
        </div>

        <div class="reference-grid">
          <section class="reference-card">
            <h5>部门字典</h5>
            <ul>
              <li v-for="department in departments" :key="department.id">
                <strong>{{ department.name }}</strong>
                <span>{{ department.id }}</span>
              </li>
            </ul>
          </section>
          <section class="reference-card">
            <h5>角色字典</h5>
            <ul>
              <li v-for="role in roles" :key="role.code">
                <strong>{{ role.name || role.code }}</strong>
                <span>{{ role.code }}</span>
              </li>
            </ul>
          </section>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ElMessage } from 'element-plus'

import { api } from '@/api'

const users = ref([])
const departments = ref([])
const roles = ref([])
const loading = ref(false)
const submitting = ref(false)

const createDefaultForm = () => ({
  username: '',
  display_name: '',
  password: '',
  role_code: '',
  primary_department_id: '',
  collaborative_departments_text: '',
})

const createForm = reactive(createDefaultForm())

const departmentNameById = computed(() =>
  Object.fromEntries((departments.value || []).map((department) => [department.id, department.name])),
)

const roleNameByCode = computed(() =>
  Object.fromEntries((roles.value || []).map((role) => [role.code, role.name || role.code])),
)

const parseCollaborativeDepartmentIds = (text) =>
  [...new Set(String(text || '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean))]

const formatCollaborativeDepartments = (departmentIds = []) => {
  if (!departmentIds?.length) {
    return '-'
  }

  return departmentIds
    .map((departmentId) => departmentNameById.value[departmentId] || departmentId)
    .join('、')
}

const resetCreateForm = () => {
  Object.assign(createForm, createDefaultForm())
}

const loadData = async () => {
  loading.value = true
  try {
    const [usersRes, departmentsRes, rolesRes] = await Promise.all([
      api.getUsers(1, 100),
      api.getDepartments(),
      api.getRoles(),
    ])
    users.value = usersRes.data?.items || []
    departments.value = departmentsRes.data || []
    roles.value = rolesRes.data || []
  } finally {
    loading.value = false
  }
}

const handleCreateUser = async () => {
  if (submitting.value) {
    return
  }

  if (!createForm.username || !createForm.password || !createForm.display_name || !createForm.role_code || !createForm.primary_department_id) {
    ElMessage.warning('请填写完整的用户信息')
    return
  }

  submitting.value = true
  try {
    await api.createUser({
      username: createForm.username,
      password: createForm.password,
      display_name: createForm.display_name,
      role_code: createForm.role_code,
      primary_department_id: createForm.primary_department_id,
      collaborative_department_ids: parseCollaborativeDepartmentIds(createForm.collaborative_departments_text),
    })
    ElMessage.success('用户创建成功')
    resetCreateForm()
    await loadData()
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped lang="scss">
.admin-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header,
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.page-header h3,
.panel-head h4 {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink-strong);
  margin-bottom: 4px;
}

.page-header p,
.panel-head p {
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink-muted);
}

.admin-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(340px, 0.9fr);
  gap: 20px;
  align-items: start;
}

.panel-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ghost-button,
.primary-button {
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-button {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink-strong);
}

.primary-button {
  border: 1px solid #1D4ED8;
  background: #1D4ED8;
  color: #fff;
}

.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;

  th,
  td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
  }

  thead th {
    font-size: 12px;
    color: var(--ink-muted);
    font-weight: 600;
    background: var(--bg-subtle);
  }
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  span {
    font-size: 12px;
    color: var(--ink-muted);
  }

  input,
  select {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    font-size: 13px;
    color: var(--ink-strong);
    background: #fff;
  }
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.reference-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  padding: 14px;

  h5 {
    margin-bottom: 10px;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-strong);
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  li {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
    color: var(--ink-muted);
  }

  strong {
    color: var(--ink-strong);
    font-weight: 600;
  }
}

.empty-copy {
  padding: 20px;
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  border: 1px dashed var(--line);
  color: var(--ink-muted);
  font-size: 13px;
}

@media (max-width: 1080px) {
  .admin-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .form-grid,
  .reference-grid {
    grid-template-columns: 1fr;
  }

  .page-header,
  .panel-head {
    flex-direction: column;
  }
}
</style>
