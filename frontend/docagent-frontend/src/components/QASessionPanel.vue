<template>
  <section class="shell-panel qa-session-panel">
    <div class="panel-head">
      <div>
        <p class="section-label">回答面板</p>
        <h3 class="panel-title">检索增强问答</h3>
      </div>
      <span class="badge" :class="loading ? 'badge-blue' : 'badge-gray'">
        {{ loading ? '生成中' : sessionId ? '已完成' : '待提问' }}
      </span>
    </div>

    <p v-if="scopeLabel" class="scope-copy">{{ scopeLabel }}</p>

    <div v-if="answer" class="answer-body">
      {{ answer }}
    </div>
    <div v-else class="answer-empty">
      输入问题后，系统会基于文档证据逐段返回答案。
    </div>

    <div v-if="citations.length" class="citation-block">
      <p class="citation-label">引用文档</p>
      <div class="citation-list">
        <span
          v-for="citation in citations"
          :key="citation.doc_id"
          class="citation-chip"
        >
          {{ citation.filename || citation.doc_id }}
        </span>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  answer: {
    type: String,
    default: '',
  },
  citations: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  sessionId: {
    type: String,
    default: '',
  },
  scopeLabel: {
    type: String,
    default: '',
  },
})
</script>

<style scoped lang="scss">
.qa-session-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 320px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--ink-strong);
  margin-top: 4px;
}

.scope-copy {
  color: var(--ink-muted);
  font-size: 13px;
}

.answer-body {
  flex: 1;
  background: linear-gradient(180deg, #F8FAFC 0%, #EFF6FF 100%);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px;
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--ink-body);
}

.answer-empty {
  flex: 1;
  border: 1px dashed var(--line-strong);
  border-radius: 16px;
  padding: 18px;
  color: var(--ink-muted);
  display: grid;
  place-items: center;
  text-align: center;
  min-height: 180px;
}

.citation-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.citation-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-light);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.citation-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.citation-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--blue-50);
  color: var(--blue-700);
  font-size: 12px;
  font-weight: 600;
}
</style>
