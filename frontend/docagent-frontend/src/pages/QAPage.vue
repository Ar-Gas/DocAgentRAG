<template>
  <section class="qa-page">
    <div class="qa-hero shell-panel">
      <div>
        <p class="section-label">Ask With Evidence</p>
        <h2 class="hero-title">对文档仓库发起证据驱动问答</h2>
        <p class="hero-copy">
          先选择文档范围，再提出问题。答案会随着后端流式返回逐步展开。
        </p>
      </div>
      <div class="hero-metrics">
        <div>
          <span>可用文档</span>
          <strong>{{ documents.length }}</strong>
        </div>
        <div>
          <span>当前范围</span>
          <strong>{{ selectedDocIds.length || '全部' }}</strong>
        </div>
      </div>
    </div>

    <div class="qa-grid">
      <section class="shell-panel qa-controls">
        <div class="controls-head">
          <div>
            <p class="section-label">文档范围</p>
            <h3 class="controls-title">选择上下文</h3>
          </div>
          <button type="button" class="text-action" @click="clearScope">清空</button>
        </div>

        <div class="doc-chip-list">
          <button
            v-for="doc in documents"
            :key="doc.id"
            type="button"
            class="doc-chip"
            :class="{ 'doc-chip--active': selectedDocIds.includes(doc.id) }"
            @click="toggleDocument(doc.id)"
          >
            <span class="doc-chip__name">{{ doc.filename }}</span>
            <span class="doc-chip__meta">{{ doc.file_type || '文档' }}</span>
          </button>
        </div>

        <div class="divider"></div>

        <label class="question-label" for="qa-question">问题</label>
        <textarea
          id="qa-question"
          v-model="question"
          class="qa-question-input"
          rows="6"
          placeholder="例如：这些文档对联邦学习中的隐私保护给出了哪些不同观点？"
        />

        <div class="control-actions">
          <button
            type="button"
            class="qa-submit-btn"
            :disabled="loading || !question.trim()"
            @click="submitQuestion"
          >
            {{ loading ? '生成中...' : '开始问答' }}
          </button>
          <p class="helper-copy">
            {{ selectedDocIds.length ? `已限定 ${selectedDocIds.length} 个文档` : '未选择文档时会检索全部文档' }}
          </p>
        </div>

        <p v-if="error" class="error-copy">{{ error }}</p>
      </section>

      <QASessionPanel
        :answer="answer"
        :citations="selectedDocuments"
        :loading="loading"
        :session-id="sessionId"
        :scope-label="scopeLabel"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import QASessionPanel from '@/components/QASessionPanel.vue'
import { api } from '@/api'

const documents = ref([])
const selectedDocIds = ref([])
const question = ref('')
const answer = ref('')
const error = ref('')
const loading = ref(false)
const sessionId = ref('')
let cancelStream = null

const selectedDocuments = computed(() => (
  documents.value.filter((doc) => selectedDocIds.value.includes(doc.id))
))

const scopeLabel = computed(() => {
  if (!selectedDocIds.value.length) {
    return '当前范围：全部文档'
  }
  return `当前范围：${selectedDocuments.value.map((doc) => doc.filename).join('、')}`
})

const loadDocuments = async () => {
  const response = await api.getDocumentList(1, 100)
  documents.value = response.data?.items || []
}

const toggleDocument = (documentId) => {
  if (selectedDocIds.value.includes(documentId)) {
    selectedDocIds.value = selectedDocIds.value.filter((id) => id !== documentId)
    return
  }
  selectedDocIds.value = [...selectedDocIds.value, documentId]
}

const clearScope = () => {
  selectedDocIds.value = []
}

const resetAnswerState = () => {
  answer.value = ''
  error.value = ''
  sessionId.value = ''
}

const submitQuestion = () => {
  if (!question.value.trim()) return

  if (cancelStream) {
    cancelStream()
    cancelStream = null
  }

  resetAnswerState()
  loading.value = true

  cancelStream = api.streamQA(
    {
      query: question.value.trim(),
      doc_ids: selectedDocIds.value.length ? selectedDocIds.value : null,
    },
    {
      onMessage(payload) {
        answer.value += payload.chunk || ''
      },
      onDone(payload) {
        sessionId.value = payload.session_id || ''
        loading.value = false
      },
      onError(streamError) {
        error.value = streamError.message || '问答请求失败'
        loading.value = false
      },
    }
  )
}

onMounted(() => {
  loadDocuments()
})

onBeforeUnmount(() => {
  cancelStream?.()
})
</script>

<style scoped lang="scss">
.qa-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.qa-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.18), transparent 38%),
    linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 58%, #EFF6FF 100%);
}

.hero-title {
  font-size: 28px;
  line-height: 1.2;
  color: var(--ink-strong);
  margin-top: 6px;
}

.hero-copy {
  margin-top: 10px;
  max-width: 620px;
  color: var(--ink-muted);
}

.hero-metrics {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;

  div {
    min-width: 120px;
    padding: 14px 16px;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(148, 163, 184, 0.25);
  }

  span {
    display: block;
    color: var(--ink-light);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  strong {
    display: block;
    margin-top: 6px;
    font-size: 24px;
    color: var(--ink-strong);
  }
}

.qa-grid {
  display: grid;
  grid-template-columns: 400px 1fr;
  gap: 20px;
  align-items: start;
}

.qa-controls {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.controls-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.controls-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--ink-strong);
  margin-top: 4px;
}

.text-action {
  border: none;
  background: transparent;
  color: var(--blue-700);
  font-weight: 600;
  cursor: pointer;
}

.doc-chip-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 280px;
  overflow-y: auto;
}

.doc-chip {
  width: 100%;
  text-align: left;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 16px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;

  &:hover {
    border-color: var(--line-strong);
    box-shadow: var(--shadow-sm);
    transform: translateY(-1px);
  }

  &--active {
    border-color: var(--blue-600);
    background: linear-gradient(180deg, #FFFFFF 0%, #EFF6FF 100%);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  }
}

.doc-chip__name {
  display: block;
  color: var(--ink-strong);
  font-weight: 600;
}

.doc-chip__meta {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--ink-muted);
}

.question-label {
  font-weight: 600;
  color: var(--ink-strong);
}

.qa-question-input {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 16px;
  resize: vertical;
  min-height: 150px;
  background: #fff;

  &:focus {
    outline: none;
    border-color: var(--blue-600);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }
}

.control-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.qa-submit-btn {
  border: none;
  background: linear-gradient(135deg, var(--blue-700) 0%, var(--blue-600) 100%);
  color: #fff;
  padding: 12px 18px;
  border-radius: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-sm);

  &:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
}

.helper-copy {
  color: var(--ink-muted);
  font-size: 12px;
}

.error-copy {
  color: var(--red-600);
  font-size: 13px;
}

@media (max-width: 1024px) {
  .qa-hero,
  .qa-grid {
    grid-template-columns: 1fr;
    display: grid;
  }
}
</style>
