<template>
  <el-drawer
    :model-value="visible"
    size="42rem"
    title="分类报告"
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="drawer-stack">
      <el-skeleton v-if="loading" animated :rows="8" />

      <template v-else-if="report">
        <section class="drawer-card">
          <div class="drawer-head">
            <div>
              <h4>{{ report.title || '分类报告' }}</h4>
              <p>{{ report.summary }}</p>
            </div>
            <el-tag :type="report.llm_used ? 'warning' : 'info'">
              {{ report.llm_used ? 'LLM' : '规则分组' }}
            </el-tag>
          </div>
        </section>

        <section
          v-for="row in report.rows || []"
          :key="row.label"
          class="drawer-card report-row"
        >
          <div class="row-head">
            <h5>{{ row.label }}</h5>
            <el-tag type="success">{{ row.document_count }} 篇</el-tag>
          </div>
          <p>{{ row.summary }}</p>
          <div class="tag-row">
            <el-tag
              v-for="keyword in row.keywords || []"
              :key="`${row.label}-${keyword}`"
              size="small"
              type="info"
            >
              {{ keyword }}
            </el-tag>
          </div>
          <div class="document-row" v-if="row.representative_documents?.length">
            <span
              v-for="filename in row.representative_documents"
              :key="`${row.label}-${filename}`"
            >
              {{ filename }}
            </span>
          </div>
        </section>
      </template>

      <el-empty v-else description="还没有生成分类报告。" />
    </div>
  </el-drawer>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  report: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible'])
</script>

<style scoped lang="scss">
.drawer-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-card {
  padding: 16px;
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  border: 1px solid var(--line);
}

.drawer-head,
.row-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.drawer-head {
  margin-bottom: 8px;

  h4 {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-strong);
  }
}

.row-head {
  margin-bottom: 8px;

  h5 {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-strong);
  }
}

.drawer-head p,
.report-row p {
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-muted);
}

.tag-row,
.document-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.document-row span {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  font-size: 12px;
  color: var(--ink-body);
}
</style>
