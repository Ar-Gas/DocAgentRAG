<template>
  <section class="search-toolbar shell-panel">
    <div class="toolbar-head">
      <div class="toolbar-title-group">
        <h3>具体检索</h3>
        <p>围绕公共文档、部门文档和业务分类执行检索，结果仅返回当前权限范围内的治理文档。</p>
      </div>

      <div class="toolbar-metrics">
        <div class="metric-item">
          <span>文档总量</span>
          <strong>{{ stats.total_documents || 0 }}</strong>
        </div>
        <div class="metric-divider"></div>
        <div class="metric-item">
          <span>已向量化</span>
          <strong>{{ stats.vector_indexed_documents || 0 }}</strong>
        </div>
      </div>
    </div>

    <div class="query-row">
      <el-input
        :model-value="form.query"
        class="main-query"
        clearable
        placeholder="输入问题、业务术语或文档标题"
        @update:model-value="updateField('query', $event)"
        @keyup.enter="emit('search')"
      />

      <el-select
        :model-value="form.mode"
        class="mode-select"
        @update:model-value="updateField('mode', $event)"
      >
        <el-option label="混合检索" value="hybrid" />
        <el-option label="向量检索" value="vector" />
        <el-option label="关键词检索" value="keyword" />
      </el-select>

      <el-button type="primary" :loading="loading" @click="emit('search')">检索文档</el-button>
    </div>

    <div class="filter-grid">
      <label class="field-block">
        <span>文件名</span>
        <el-input
          :model-value="form.filename"
          clearable
          placeholder="按名称过滤"
          @update:model-value="updateField('filename', $event)"
          @keyup.enter="emit('search')"
        />
      </label>

      <label class="field-block">
        <span>文件类型</span>
        <el-select
          :model-value="form.file_types"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="全部类型"
          @update:model-value="updateField('file_types', $event)"
        >
          <el-option
            v-for="type in fileTypeOptions"
            :key="type"
            :label="type"
            :value="type"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>一级分类</span>
        <el-select
          :model-value="form.visibility_scope"
          clearable
          placeholder="全部可见文档"
          @update:model-value="updateField('visibility_scope', $event || '')"
        >
          <el-option label="公共文档" value="public" />
          <el-option label="部门文档" value="department" />
        </el-select>
      </label>

      <label class="field-block">
        <span>归属部门</span>
        <el-select
          :model-value="form.department_id"
          clearable
          placeholder="全部部门"
          @update:model-value="updateField('department_id', $event || '')"
        >
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
        <el-select
          :model-value="form.business_category_id"
          clearable
          placeholder="全部业务分类"
          @update:model-value="updateField('business_category_id', $event || '')"
        >
          <el-option
            v-for="category in categories"
            :key="category.id"
            :label="formatCategoryLabel(category)"
            :value="category.id"
          />
        </el-select>
      </label>

      <label class="field-block">
        <span>日期范围</span>
        <el-date-picker
          :model-value="form.date_range"
          type="daterange"
          value-format="YYYY-MM-DD"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          @update:model-value="updateField('date_range', $event || [])"
        />
      </label>
    </div>

    <div class="action-row">
      <div class="mode-note">
        <strong>{{ modeTitle }}</strong>
        <p>{{ modeDescription }}</p>
      </div>

      <div class="action-group">
        <el-button @click="emit('reset')">清空</el-button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true
  },
  stats: {
    type: Object,
    default: () => ({})
  },
  departments: {
    type: Array,
    default: () => []
  },
  categories: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'update:modelValue',
  'search',
  'reset'
])

const form = computed(() => props.modelValue || {})
const fileTypeOptions = computed(() => Object.keys(props.stats.file_types || {}))

const modeMeta = computed(() => {
  const currentMode = form.value.mode || 'hybrid'
  const dictionary = {
    hybrid: {
      title: '混合检索',
      description: '向量召回与关键词召回并行，适合跨部门治理资料的日常检索。'
    },
    vector: {
      title: '向量检索',
      description: '优先匹配内容接近的资料，适合制度问答和背景检索。'
    },
    keyword: {
      title: '关键词检索',
      description: '适合项目代号、文件名、条款术语和精确短语检索。'
    }
  }
  return dictionary[currentMode] || dictionary.hybrid
})

const modeTitle = computed(() => modeMeta.value.title)
const modeDescription = computed(() => modeMeta.value.description)

const formatCategoryLabel = (category) => {
  const scopeLabel = category?.scope_type === 'department' ? '部门' : '公共'
  return `${category?.name || category?.id || '未命名分类'} · ${scopeLabel}`
}

const updateField = (field, value) => {
  emit('update:modelValue', {
    ...form.value,
    [field]: value
  })
}
</script>

<style scoped lang="scss">
.search-toolbar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
}

.toolbar-title-group {
  h3 {
    font-size: 15px;
    font-weight: 600;
    color: var(--ink-strong);
    margin-bottom: 4px;
  }

  p {
    font-size: 12px;
    color: var(--ink-muted);
  }
}

.toolbar-metrics {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.metric-item {
  text-align: center;
  span {
    display: block;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--ink-muted);
    margin-bottom: 2px;
  }
  strong {
    font-size: 20px;
    font-weight: 700;
    color: var(--ink-strong);
    letter-spacing: -0.02em;
  }
}

.metric-divider {
  width: 1px;
  height: 28px;
  background: var(--line);
}

.query-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.main-query {
  flex: 1;
}

.mode-select {
  width: 150px;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.action-row {
  display: flex;
  gap: 14px;
  justify-content: space-between;
  align-items: stretch;
}

.mode-note {
  flex: 1;
  min-width: 0;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: var(--ink-strong);
  color: rgba(255, 255, 255, 0.88);

  strong {
    display: block;
    margin-bottom: 4px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #93C5FD;
  }

  p {
    font-size: 12px;
    line-height: 1.6;
    color: #94A3B8;
  }
}

.action-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-end;
}

@media (max-width: 1180px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 860px) {
  .toolbar-head,
  .query-row,
  .action-row {
    flex-direction: column;
  }

  .filter-grid {
    grid-template-columns: 1fr;
  }

  .mode-select {
    width: 100%;
  }

  .action-group {
    justify-content: flex-start;
  }
}
</style>
