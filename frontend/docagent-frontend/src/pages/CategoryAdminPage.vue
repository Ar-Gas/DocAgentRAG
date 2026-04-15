<template>
  <section class="admin-page">
    <div class="page-header shell-panel">
      <div>
        <h3>分类管理</h3>
        <p>一级按公共文档 / 部门文档控制权限，二级按业务分类维护企业统一口径。</p>
      </div>
      <button type="button" class="ghost-button" :disabled="loading" @click="loadData">
        {{ loading ? '加载中…' : '刷新分类' }}
      </button>
    </div>

    <div class="admin-grid">
      <article class="shell-panel panel-stack">
        <div class="panel-head">
          <div>
            <h4>公共业务分类</h4>
            <p>系统管理员维护全公司统一分类。</p>
          </div>
        </div>

        <form v-if="canManageSystemCategories" class="form-grid" @submit.prevent="handleCreateSystemCategory">
          <label>
            <span>分类名称</span>
            <input v-model.trim="systemForm.name" type="text" placeholder="例如 制度流程" />
          </label>
          <label>
            <span>状态</span>
            <select v-model="systemForm.status">
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </select>
          </label>
          <label>
            <span>排序</span>
            <input v-model.number="systemForm.sort_order" type="number" min="0" />
          </label>
          <div class="panel-actions">
            <button type="button" class="primary-button" :disabled="submitting" @click="handleCreateSystemCategory">
              新建公共分类
            </button>
          </div>
        </form>

        <div v-if="loading" class="empty-copy">正在加载系统分类…</div>
        <ul v-else class="record-list">
          <li v-for="category in systemCategories" :key="category.id" class="record-item">
            <div>
              <strong>{{ category.name }}</strong>
              <span>{{ category.status === 'enabled' ? '启用' : '停用' }} · 排序 {{ category.sort_order || 0 }}</span>
            </div>
            <button
              v-if="canManageSystemCategories"
              type="button"
              class="link-button"
              @click="toggleCategoryStatus(category)"
            >
              {{ category.status === 'enabled' ? '停用' : '启用' }}
            </button>
          </li>
          <li v-if="!systemCategories.length" class="empty-copy">暂无公共业务分类。</li>
        </ul>
      </article>

      <article class="shell-panel panel-stack">
        <div class="panel-head">
          <div>
            <h4>部门业务分类</h4>
            <p>部门管理员只维护自己负责的部门分类。</p>
          </div>
        </div>

        <form v-if="manageableDepartments.length" class="form-grid" @submit.prevent="handleCreateDepartmentCategory">
          <label>
            <span>归属部门</span>
            <select v-model="departmentForm.department_id">
              <option value="">请选择部门</option>
              <option v-for="department in manageableDepartments" :key="department.id" :value="department.id">
                {{ department.name }}
              </option>
            </select>
          </label>
          <label>
            <span>分类名称</span>
            <input v-model.trim="departmentForm.name" type="text" placeholder="例如 预算管理" />
          </label>
          <label>
            <span>状态</span>
            <select v-model="departmentForm.status">
              <option value="enabled">启用</option>
              <option value="disabled">停用</option>
            </select>
          </label>
          <label>
            <span>排序</span>
            <input v-model.number="departmentForm.sort_order" type="number" min="0" />
          </label>
          <div class="panel-actions">
            <button type="button" class="primary-button" :disabled="submitting" @click="handleCreateDepartmentCategory">
              新建部门分类
            </button>
          </div>
        </form>

        <div v-if="loading" class="empty-copy">正在加载部门分类…</div>
        <div v-else-if="departmentCategoryGroups.length" class="group-stack">
          <section
            v-for="group in departmentCategoryGroups"
            :key="group.department.id"
            class="group-card"
          >
            <div class="group-head">
              <strong>{{ group.department.name }}</strong>
              <span>{{ group.categories.length }} 个分类</span>
            </div>
            <ul class="record-list">
              <li v-for="category in group.categories" :key="category.id" class="record-item">
                <div>
                  <strong>{{ category.name }}</strong>
                  <span>{{ category.status === 'enabled' ? '启用' : '停用' }} · 排序 {{ category.sort_order || 0 }}</span>
                </div>
                <button type="button" class="link-button" @click="toggleCategoryStatus(category)">
                  {{ category.status === 'enabled' ? '停用' : '启用' }}
                </button>
              </li>
            </ul>
          </section>
        </div>
        <div v-else class="empty-copy">
          {{ manageableDepartments.length ? '当前部门下还没有业务分类。' : '当前会话未返回可管理部门。' }}
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { ElMessage } from 'element-plus'

import { api } from '@/api'
import { sessionStore } from '@/stores/session'

const loading = ref(false)
const submitting = ref(false)
const departments = ref([])
const systemCategories = ref([])
const departmentCategoryGroups = ref([])

const currentUser = computed(() => sessionStore.state.user || {})
const roleCode = computed(() => currentUser.value?.role_code || '')

const uniqueIds = (values = []) =>
  [...new Set((values || []).map((value) => String(value || '').trim()).filter(Boolean))]

const managedDepartmentIds = computed(() => uniqueIds(currentUser.value?.managed_department_ids))
const canManageSystemCategories = computed(() => roleCode.value === 'system_admin')

const manageableDepartments = computed(() => {
  if (roleCode.value === 'system_admin') {
    return departments.value
  }

  const managedSet = new Set(managedDepartmentIds.value)
  return departments.value.filter((department) => managedSet.has(String(department.id)))
})

const createDefaultSystemForm = () => ({
  name: '',
  sort_order: 0,
  status: 'enabled',
})

const createDefaultDepartmentForm = () => ({
  department_id: '',
  name: '',
  sort_order: 0,
  status: 'enabled',
})

const systemForm = reactive(createDefaultSystemForm())
const departmentForm = reactive(createDefaultDepartmentForm())

const syncDepartmentForm = () => {
  if (departmentForm.department_id && manageableDepartments.value.some((item) => item.id === departmentForm.department_id)) {
    return
  }
  departmentForm.department_id = manageableDepartments.value[0]?.id || ''
}

const resetForms = () => {
  Object.assign(systemForm, createDefaultSystemForm())
  Object.assign(departmentForm, createDefaultDepartmentForm())
  syncDepartmentForm()
}

const loadData = async () => {
  loading.value = true
  try {
    const [departmentsRes, systemCategoriesRes] = await Promise.all([
      api.getDepartments(),
      api.getSystemCategories(),
    ])

    departments.value = departmentsRes.data || []
    systemCategories.value = systemCategoriesRes.data || []
    syncDepartmentForm()

    const groups = await Promise.all(
      manageableDepartments.value.map(async (department) => {
        const response = await api.getDepartmentCategories(department.id)
        return {
          department,
          categories: response.data || [],
        }
      }),
    )
    departmentCategoryGroups.value = groups
  } finally {
    loading.value = false
  }
}

const handleCreateSystemCategory = async () => {
  if (submitting.value) {
    return
  }
  if (!systemForm.name) {
    ElMessage.warning('请输入公共分类名称')
    return
  }

  submitting.value = true
  try {
    await api.createSystemCategory({ ...systemForm })
    ElMessage.success('公共分类已创建')
    Object.assign(systemForm, createDefaultSystemForm())
    await loadData()
  } finally {
    submitting.value = false
  }
}

const handleCreateDepartmentCategory = async () => {
  if (submitting.value) {
    return
  }
  if (!departmentForm.department_id || !departmentForm.name) {
    ElMessage.warning('请选择部门并输入分类名称')
    return
  }

  submitting.value = true
  try {
    await api.createDepartmentCategory({ ...departmentForm })
    ElMessage.success('部门分类已创建')
    Object.assign(departmentForm, createDefaultDepartmentForm())
    syncDepartmentForm()
    await loadData()
  } finally {
    submitting.value = false
  }
}

const toggleCategoryStatus = async (category) => {
  const nextStatus = category.status === 'enabled' ? 'disabled' : 'enabled'
  await api.updateCategory(category.id, { status: nextStatus })
  ElMessage.success(`分类已${nextStatus === 'enabled' ? '启用' : '停用'}`)
  await loadData()
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
.panel-head,
.group-head {
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}

.panel-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  align-items: end;
  justify-content: flex-end;
}

.ghost-button,
.primary-button,
.link-button {
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

.link-button {
  border: 1px solid var(--line);
  background: var(--bg-subtle);
  color: var(--ink-strong);
}

.record-list,
.group-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.record-item,
.group-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  padding: 14px;
}

.record-item strong,
.group-head strong {
  display: block;
  color: var(--ink-strong);
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 3px;
}

.record-item span,
.group-head span {
  font-size: 12px;
  color: var(--ink-muted);
}

.group-card {
  flex-direction: column;
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
  .form-grid {
    grid-template-columns: 1fr;
  }

  .page-header,
  .panel-head,
  .group-head,
  .record-item {
    flex-direction: column;
  }
}
</style>
