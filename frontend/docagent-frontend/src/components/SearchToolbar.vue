<template>
  <section class="search-toolbar shell-panel">
    <div class="toolbar-head">
      <div class="toolbar-title-group">
        <h3>智能检索</h3>
        <p>输入问题或关键词，检索文档库并进入提取文本阅读区。</p>
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
        <el-option label="语义检索" value="vector" />
        <el-option label="关键词检索" value="keyword" />
        <el-option label="智能检索" value="smart" />
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
        <span>业务分类</span>
        <el-select
          :model-value="form.classification"
          clearable
          placeholder="全部分类"
          @update:model-value="updateField('classification', $event)"
        >
          <el-option label="全部分类" value="" />
          <el-option-group
            v-for="group in groupedCategories"
            :key="group.domain"
            :label="group.domain"
          >
            <el-option
              v-for="category in group.options"
              :key="category.id"
              :label="category.label"
              :value="category.id"
            />
          </el-option-group>
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

    <div class="tuning-row">
      <label v-if="form.mode === 'hybrid'" class="slider-block">
        <span>语义权重</span>
        <el-slider
          :model-value="Math.round((form.alpha || 0.5) * 100)"
          @update:model-value="updateAlpha"
        />
      </label>

      <label v-if="form.mode !== 'keyword'" class="switch-block">
        <span>启用重排序</span>
        <el-switch
          :model-value="form.use_rerank"
          @update:model-value="updateField('use_rerank', $event)"
        />
      </label>

      <label v-if="form.mode === 'smart'" class="switch-block">
        <span>查询扩展</span>
        <el-switch
          :model-value="form.use_query_expansion"
          @update:model-value="updateField('use_query_expansion', $event)"
        />
      </label>

      <label v-if="form.mode === 'smart'" class="switch-block">
        <span>LLM 重排</span>
        <el-switch
          :model-value="form.use_llm_rerank"
          @update:model-value="updateField('use_llm_rerank', $event)"
        />
      </label>
    </div>

    <div class="action-row">
      <div class="mode-note">
        <strong>{{ modeTitle }}</strong>
        <p>{{ modeDescription }}</p>
      </div>

      <div class="action-group">
        <el-button :disabled="!canSummarize" @click="emit('summarize')">
          <el-icon><Document /></el-icon>LLM 总结
        </el-button>
        <el-button :disabled="!canGenerateReport" @click="emit('generate-report')">分类报告</el-button>
        <el-button :loading="rebuildingTopics" @click="emit('rebuild-topics')">重建主题树</el-button>
        <el-button @click="emit('reset')">清空</el-button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true
  },
  stats: {
    type: Object,
    default: () => ({})
  },
  categories: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  canSummarize: {
    type: Boolean,
    default: false
  },
  canGenerateReport: {
    type: Boolean,
    default: false
  },
  rebuildingTopics: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'update:modelValue',
  'search',
  'reset',
  'summarize',
  'generate-report',
  'rebuild-topics'
])

const form = computed(() => props.modelValue || {})
const fileTypeOptions = computed(() => Object.keys(props.stats.file_types || {}))

const normalizeCategory = (category) => {
  if (typeof category === 'string') {
    return {
      id: category,
      label: category,
      path: [],
      domain: '未分组'
    }
  }

  const path = Array.isArray(category?.path) ? category.path.filter(Boolean) : []
  const label = category?.label || path.at(-1) || category?.id || ''
  return {
    id: category?.id || label,
    label,
    path,
    domain: category?.domain || path[0] || '未分组'
  }
}

const groupedCategories = computed(() => {
  const groups = new Map()

  ;(props.categories || [])
    .map(normalizeCategory)
    .filter(category => category.id && category.label)
    .forEach((category) => {
      if (!groups.has(category.domain)) {
        groups.set(category.domain, [])
      }
      groups.get(category.domain).push(category)
    })

  return Array.from(groups.entries()).map(([domain, options]) => ({
    domain,
    options
  }))
})

const modeMeta = computed(() => {
  const currentMode = form.value.mode || 'hybrid'
  const dictionary = {
    hybrid: {
      title: '混合检索',
      description: '向量召回和关键词召回一起工作，适合办公资料的日常查找。'
    },
    vector: {
      title: '语义检索',
      description: '更适合问句和概念性检索，优先理解语义接近的文档。'
    },
    keyword: {
      title: '关键词检索',
      description: '更适合项目代号、文件名、术语和精确短语。'
    },
    smart: {
      title: '智能检索',
      description: '在混合检索基础上叠加查询扩展与 LLM 重排，质量更高但耗时更长。'
    }
  }
  return dictionary[currentMode] || dictionary.hybrid
})

const modeTitle = computed(() => modeMeta.value.title)
const modeDescription = computed(() => modeMeta.value.description)

const updateField = (field, value) => {
  emit('update:modelValue', {
    ...form.value,
    [field]: value
  })
}

const updateAlpha = (value) => {
  updateField('alpha', value / 100)
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.field-block,
.switch-block,
.slider-block {
  display: flex;
  flex-direction: column;
  gap: 6px;

  span {
    font-size: 12px;
    font-weight: 500;
    color: var(--ink-muted);
  }
}

.tuning-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.switch-block,
.slider-block {
  min-width: 160px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: var(--bg-subtle);
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
