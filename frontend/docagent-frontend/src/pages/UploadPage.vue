<template>
  <section class="upload-page">
    <div class="page-header shell-panel">
      <div>
        <h3>上传文档</h3>
        <p>上传时请显式填写治理元数据，包括可见范围、归属部门和业务分类，确保台账口径一致。</p>
      </div>
      <div class="summary-chips">
        <span class="summary-chip">一级范围：公共文档 / 部门文档</span>
        <span class="summary-chip">业务分类：按治理目录维护</span>
      </div>
    </div>

    <FileUpload
      :departments="allowedDepartments"
      :system-categories="systemCategories"
      :default-department-id="defaultDepartmentId"
      :access-note="accessNote"
      @upload-success="emit('upload-success')"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import FileUpload from '@/components/FileUpload.vue'
import { api } from '@/api'
import { sessionStore } from '@/stores/session'

const emit = defineEmits(['upload-success'])

const departments = ref([])
const systemCategories = ref([])

const currentUser = computed(() => sessionStore.state.user || {})
const roleCode = computed(() => currentUser.value?.role_code || '')

const uniqueIds = (values = []) =>
  [...new Set((values || []).map((value) => String(value || '').trim()).filter(Boolean))]

const allowedDepartmentIds = computed(() => {
  if (roleCode.value === 'system_admin' || roleCode.value === 'audit_readonly') {
    return []
  }

  if (roleCode.value === 'department_admin') {
    return uniqueIds(currentUser.value?.managed_department_ids)
  }

  return uniqueIds([
    currentUser.value?.primary_department_id,
    ...(currentUser.value?.collaborative_department_ids || []),
  ])
})

const allowedDepartments = computed(() => {
  if (!allowedDepartmentIds.value.length) {
    return departments.value
  }

  const allowedSet = new Set(allowedDepartmentIds.value)
  return departments.value.filter((department) => allowedSet.has(String(department.id)))
})

const defaultDepartmentId = computed(() => {
  const preferredId = allowedDepartmentIds.value[0]
  if (preferredId && allowedDepartments.value.some((department) => String(department.id) === preferredId)) {
    return preferredId
  }
  return allowedDepartments.value[0]?.id ? String(allowedDepartments.value[0].id) : ''
})

const accessNote = computed(() => {
  if (roleCode.value === 'employee' && !allowedDepartmentIds.value.length && departments.value.length) {
    return '当前登录会话未返回部门归属信息，前端暂不限制可选部门，实际权限仍以后端校验为准。'
  }

  if (roleCode.value === 'department_admin' && allowedDepartmentIds.value.length) {
    return `当前只展示你可管理的 ${allowedDepartmentIds.value.length} 个部门。`
  }

  return ''
})

const loadReferenceData = async () => {
  const [departmentsResponse, systemCategoriesResponse] = await Promise.all([
    api.getDepartments(),
    api.getSystemCategories(),
  ])

  departments.value = departmentsResponse.data || []
  systemCategories.value = systemCategoriesResponse.data || []
}

onMounted(() => {
  loadReferenceData()
})
</script>

<style scoped lang="scss">
.upload-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--ink-strong);
    margin-bottom: 6px;
  }

  p {
    font-size: 13px;
    line-height: 1.6;
    color: var(--ink-muted);
  }
}

.summary-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.summary-chip {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--bg-subtle);
  font-size: 12px;
  color: var(--ink-muted);
}

@media (max-width: 860px) {
  .page-header {
    flex-direction: column;
  }

  .summary-chips {
    justify-content: flex-start;
  }
}
</style>
