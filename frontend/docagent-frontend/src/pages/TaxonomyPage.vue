<template>
  <section class="page-stack">
    <div class="page-intro shell-panel">
      <div>
        <p class="eyebrow">Taxonomy</p>
        <h3>动态语义主题树</h3>
        <p>基于当前语料自动生成语义主题，而不是依赖固定模板分类。</p>
      </div>
      <div class="topic-metrics">
        <div>
          <span>主题数</span>
          <strong>{{ topicCount }}</strong>
        </div>
        <div>
          <span>文档数</span>
          <strong>{{ topicTree.total_documents || 0 }}</strong>
        </div>
      </div>
    </div>

    <TopicTreePanel
      :tree="topicTree"
      :loading="loading"
      :rebuilding="rebuilding"
      :show-rebuild="true"
      :max-documents-per-topic="8"
      @rebuild="rebuildTopicTree"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import TopicTreePanel from '@/components/TopicTreePanel.vue'
import { api } from '@/api'

const loading = ref(false)
const rebuilding = ref(false)
const topicTree = ref({ topics: [], total_documents: 0 })

const topicCount = computed(() => topicTree.value?.topics?.length || 0)

const loadTopicTree = async () => {
  loading.value = true
  try {
    const response = await api.getTopicTree()
    topicTree.value = response.data || { topics: [], total_documents: 0 }
  } finally {
    loading.value = false
  }
}

const rebuildTopicTree = async () => {
  rebuilding.value = true
  try {
    const response = await api.buildTopicTree(true)
    topicTree.value = response.data || { topics: [], total_documents: 0 }
  } finally {
    rebuilding.value = false
  }
}

onMounted(() => {
  loadTopicTree()
})
</script>

<style scoped lang="scss">
.page-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-intro {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;

  h3 {
    font-size: 30px;
    color: #162948;
    margin-bottom: 8px;
  }

  p {
    color: #5a6d82;
    line-height: 1.7;
  }
}

.topic-metrics {
  display: flex;
  gap: 14px;

  div {
    min-width: 110px;
    padding: 12px 14px;
    border-radius: 16px;
    background: rgba(255, 255, 255, 0.82);
  }

  span {
    color: #8b6b40;
    font-size: 13px;
  }

  strong {
    display: block;
    margin-top: 8px;
    font-size: 28px;
    color: #162948;
  }
}

@media (max-width: 860px) {
  .page-intro {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
