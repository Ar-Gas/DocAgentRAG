<template>
  <div class="upload-card shell-panel">
    <div class="upload-header">
      <div>
        <span class="upload-title">上传文档</span>
        <p class="upload-hint">先补齐治理元数据，再把文件送入知识库。支持 PDF / Office / 邮件 / TXT / 图片，最大 500MB。</p>
      </div>
      <div v-if="accessNote" class="access-note">
        {{ accessNote }}
      </div>
    </div>

    <div class="governance-grid">
      <label class="field-block">
        <span>一级分类</span>
        <el-select v-model="form.visibility_scope">
          <el-option label="公共文档" value="public" />
          <el-option label="部门文档" value="department" />
        </el-select>
      </label>

      <label class="field-block">
        <span>归属部门</span>
        <el-select v-model="form.owner_department_id" clearable placeholder="选择归属部门">
          <el-option
            v-for="department in departments"
            :key="department.id"
            :label="department.name"
            :value="department.id"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>业务分类</span>
        <el-select v-model="form.business_category_id" clearable placeholder="选择业务分类">
          <el-option
            v-for="category in availableBusinessCategories"
            :key="category.id"
            :label="formatCategoryLabel(category)"
            :value="category.id"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>共享部门</span>
        <el-select
          v-model="form.shared_department_ids"
          multiple
          collapse-tags
          collapse-tags-tooltip
          clearable
          placeholder="按需共享给协作部门"
        >
          <el-option
            v-for="department in shareableDepartments"
            :key="department.id"
            :label="department.name"
            :value="department.id"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>角色限制</span>
        <el-select v-model="form.role_restriction" clearable placeholder="默认所有登录用户">
          <el-option
            v-for="role in roleOptions"
            :key="role.value"
            :label="role.label"
            :value="role.value"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>密级</span>
        <el-select v-model="form.confidentiality_level">
          <el-option
            v-for="level in confidentialityOptions"
            :key="level.value"
            :label="level.label"
            :value="level.value"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>文档状态</span>
        <el-select v-model="form.document_status">
          <el-option
            v-for="status in statusOptions"
            :key="status.value"
            :label="status.label"
            :value="status.value"
          />
        </el-select>
      </label>
    </div>

    <el-upload
      class="upload-zone"
      drag
      :auto-upload="false"
      :on-change="handleFileChange"
      :show-file-list="false"
      :disabled="uploading"
      accept=".pdf,.docx,.doc,.xlsx,.xls,.ppt,.pptx,.eml,.msg,.txt,.jpg,.jpeg,.png,.gif,.bmp,.webp"
    >
      <div class="drop-content">
        <el-icon class="drop-icon"><UploadFilled /></el-icon>
        <p v-if="!uploading">将文件拖到此处，或<em>点击选择</em></p>
        <p v-else>上传中，请勿关闭页面…</p>
      </div>
    </el-upload>

    <div class="governance-summary">
      <span class="summary-label">当前入库规则</span>
      <span>{{ form.visibility_scope === 'public' ? '公共文档' : '部门文档' }}</span>
      <span>{{ currentDepartmentLabel }}</span>
      <span>{{ currentCategoryLabel }}</span>
      <span>{{ currentConfidentialityLabel }}</span>
    </div>

    <div v-if="uploading" class="progress-block">
      <div class="progress-info">
        <span class="progress-name">{{ currentFileName }}</span>
        <span class="progress-pct">{{ uploadPercent }}%</span>
      </div>
      <el-progress :percentage="uploadPercent" :show-text="false" status="striped" striped-flow :duration="10" />
    </div>

    <div v-if="lastResult" class="last-result" :class="lastResult.success ? 'ok' : 'err'">
      <el-icon><component :is="lastResult.success ? 'CircleCheck' : 'CircleClose'" /></el-icon>
      <span>{{ lastResult.message }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'

import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'

import { api } from '@/api'

const props = defineProps({
  departments: {
    type: Array,
    default: () => [],
  },
  systemCategories: {
    type: Array,
    default: () => [],
  },
  defaultDepartmentId: {
    type: String,
    default: '',
  },
  accessNote: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['upload-success'])

const departmentCategories = ref([])
const uploading = ref(false)
const uploadPercent = ref(0)
const currentFileName = ref('')
const lastResult = ref(null)

const form = reactive({
  visibility_scope: 'department',
  owner_department_id: '',
  shared_department_ids: [],
  business_category_id: '',
  role_restriction: '',
  confidentiality_level: 'internal',
  document_status: 'draft',
})

const roleOptions = [
  { label: '员工', value: 'employee' },
  { label: '部门管理员', value: 'department_admin' },
  { label: '系统管理员', value: 'system_admin' },
  { label: '审计只读', value: 'audit_readonly' },
]

const confidentialityOptions = [
  { label: '内部', value: 'internal' },
  { label: '机密', value: 'confidential' },
  { label: '严格机密', value: 'restricted' },
]

const statusOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已发布', value: 'published' },
  { label: '归档', value: 'archived' },
]

const availableBusinessCategories = computed(() => {
  const merged = [...(props.systemCategories || []), ...(departmentCategories.value || [])]
  const seen = new Set()

  return merged.filter((category) => {
    const id = String(category?.id || '').trim()
    if (!id || seen.has(id)) {
      return false
    }
    seen.add(id)
    return true
  })
})

const shareableDepartments = computed(() =>
  (props.departments || []).filter(
    (department) => String(department.id) !== String(form.owner_department_id || ''),
  ),
)

const currentDepartmentLabel = computed(() => {
  const department = (props.departments || []).find(
    (item) => String(item.id) === String(form.owner_department_id || ''),
  )
  return department?.name || '未指定归属部门'
})

const currentCategoryLabel = computed(() => {
  const category = availableBusinessCategories.value.find(
    (item) => String(item.id) === String(form.business_category_id || ''),
  )
  return category ? `业务分类：${formatCategoryLabel(category)}` : '业务分类：未指定'
})

const currentConfidentialityLabel = computed(() => {
  const option = confidentialityOptions.find((item) => item.value === form.confidentiality_level)
  return `密级：${option?.label || form.confidentiality_level}`
})

const formatCategoryLabel = (category) => {
  const scopeLabel = category?.scope_type === 'department' ? '部门' : '公共'
  return `${category?.name || category?.id || '未命名分类'} · ${scopeLabel}`
}

const syncOwnerDepartment = (departments = props.departments || []) => {
  if (!departments.length) {
    form.owner_department_id = ''
    return
  }

  const departmentIds = departments.map((department) => String(department.id))
  if (form.owner_department_id && departmentIds.includes(String(form.owner_department_id))) {
    return
  }

  if (props.defaultDepartmentId && departmentIds.includes(String(props.defaultDepartmentId))) {
    form.owner_department_id = String(props.defaultDepartmentId)
    return
  }

  form.owner_department_id = String(departments[0].id)
}

const normalizeSelectedMetadata = () => {
  const categoryIds = new Set(availableBusinessCategories.value.map((category) => String(category.id)))
  if (form.business_category_id && !categoryIds.has(String(form.business_category_id))) {
    form.business_category_id = ''
  }

  const shareableIds = new Set(shareableDepartments.value.map((department) => String(department.id)))
  form.shared_department_ids = (form.shared_department_ids || []).filter((departmentId) =>
    shareableIds.has(String(departmentId)),
  )
}

const loadDepartmentCategories = async (departmentId) => {
  if (!departmentId) {
    departmentCategories.value = []
    normalizeSelectedMetadata()
    return
  }

  const response = await api.getDepartmentCategories(departmentId)
  departmentCategories.value = response.data || []
  normalizeSelectedMetadata()
}

watch(
  () => props.departments,
  (departments) => {
    syncOwnerDepartment(departments || [])
  },
  { immediate: true, deep: true },
)

watch(
  () => props.defaultDepartmentId,
  () => {
    syncOwnerDepartment(props.departments || [])
  },
)

watch(
  () => form.owner_department_id,
  (departmentId) => {
    loadDepartmentCategories(departmentId)
  },
  { immediate: true },
)

watch(
  () => form.visibility_scope,
  (scope) => {
    if (scope === 'department') {
      return
    }
    form.shared_department_ids = form.shared_department_ids.filter(Boolean)
  },
)

const validateBeforeUpload = () => {
  if (!form.owner_department_id) {
    ElMessage.warning('请先选择归属部门')
    return false
  }

  if (!form.business_category_id) {
    ElMessage.warning('请先选择业务分类')
    return false
  }

  return true
}

const handleFileChange = async (file) => {
  if (uploading.value || !validateBeforeUpload()) {
    return
  }

  const rawFile = file.raw || file

  uploading.value = true
  uploadPercent.value = 0
  currentFileName.value = rawFile.name || file.name || ''
  lastResult.value = null

  try {
    const response = await api.uploadFile(rawFile, { ...form }, (evt) => {
      if (evt.total) {
        uploadPercent.value = Math.round((evt.loaded / evt.total) * 100)
      }
    })
    uploadPercent.value = 100
    lastResult.value = {
      success: true,
      message: `${currentFileName.value} 已按治理规则上传成功`,
    }
    emit('upload-success', response.data || null)
  } catch (error) {
    lastResult.value = { success: false, message: `上传失败：${error.message || '未知错误'}` }
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped lang="scss">
.upload-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.upload-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.upload-title {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
  margin-bottom: 4px;
}

.upload-hint {
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-muted);
}

.access-note {
  max-width: 320px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: 1px solid #BFDBFE;
  background: #EFF6FF;
  color: #1D4ED8;
  font-size: 12px;
  line-height: 1.6;
}

.governance-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 6px;

  span {
    font-size: 12px;
    font-weight: 500;
    color: var(--ink-muted);
  }
}

.upload-zone {
  width: 100%;

  :deep(.el-upload-dragger) {
    width: 100%;
    height: 120px;
    border-radius: var(--radius-md);
    background: var(--bg-subtle);
    border: 2px dashed var(--line);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: border-color 0.15s, background 0.15s;

    &:hover {
      border-color: var(--blue-600);
      background: var(--blue-50);
    }
  }
}

.drop-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--ink-muted);
  font-size: 13px;

  p em {
    color: var(--blue-600);
    font-style: normal;
  }
}

.drop-icon {
  font-size: 28px;
  color: var(--ink-light);
}

.governance-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--ink-muted);

  span {
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: var(--bg-subtle);
  }
}

.summary-label {
  color: var(--ink-strong);
}

.progress-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--ink-muted);
}

.progress-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 70%;
}

.last-result {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);

  &.ok {
    background: var(--green-50);
    color: var(--green-600);
    border: 1px solid #BBF7D0;
  }

  &.err {
    background: var(--red-50);
    color: var(--red-600);
    border: 1px solid #FECACA;
  }
}

@media (max-width: 1180px) {
  .governance-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 860px) {
  .upload-header {
    flex-direction: column;
  }

  .access-note {
    max-width: none;
  }

  .governance-grid {
    grid-template-columns: 1fr;
  }
}
</style>
