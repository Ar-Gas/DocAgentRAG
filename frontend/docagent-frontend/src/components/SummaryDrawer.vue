<template>
  <el-drawer
    :model-value="visible"
    size="38rem"
    title="LLM 总结"
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="drawer-stack">
      <el-skeleton v-if="loading" animated :rows="8" />

      <template v-else-if="summary">
        <section class="drawer-card">
          <div class="drawer-head">
            <h4>总结内容</h4>
            <el-tag :type="summary.llm_used ? 'warning' : 'info'">
              {{ summary.llm_used ? 'LLM' : '规则摘要' }}
            </el-tag>
          </div>
          <p>{{ summary.summary }}</p>
        </section>

        <section class="drawer-card" v-if="summary.citations?.length">
          <div class="drawer-head">
            <h4>文档证据</h4>
          </div>
          <button
            v-for="citation in summary.citations"
            :key="`${citation.document_id}-${citation.block_id}`"
            type="button"
            class="citation-card"
            @click="emit('select-document', citation.document_id, citation.block_id || null)"
          >
            <strong>{{ citation.filename }}</strong>
            <span>{{ citation.snippet || '点击跳转到命中位置' }}</span>
          </button>
        </section>
      </template>

      <el-empty v-else description="还没有生成总结。" />
    </div>
  </el-drawer>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  summary: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'select-document'])
</script>

<style scoped lang="scss">
.drawer-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.drawer-card {
  padding: 16px;
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  border: 1px solid var(--line);

  p {
    font-size: 13px;
    line-height: 1.85;
    color: var(--ink-body);
  }
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;

  h4 {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-strong);
  }
}

.citation-card {
  width: 100%;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;

  &:hover {
    border-color: var(--blue-600);
    background: var(--blue-50);
  }

  strong,
  span {
    display: block;
    font-size: 13px;
  }

  strong {
    color: var(--ink-strong);
    font-weight: 600;
  }

  span {
    margin-top: 6px;
    color: var(--ink-muted);
    line-height: 1.6;
  }
}
</style>
