<template>
  <section class="graph-page">
    <div class="graph-hero shell-panel">
      <div>
        <p class="section-label">Topic Graph</p>
        <h2 class="hero-title">查看文档中的主题连接与关系脉络</h2>
        <p class="hero-copy">
          图谱视图把实体节点和文档关系聚合到一起，便于快速观察主题密度和主要连接。
        </p>
      </div>
      <div class="hero-actions">
        <input
          v-model.trim="docFilter"
          type="text"
          class="filter-input"
          placeholder="按文档 ID 过滤，例如 doc-1"
          @keyup.enter="loadGraph"
        />
        <button type="button" class="refresh-btn" @click="loadGraph">
          刷新图谱
        </button>
      </div>
    </div>

    <div class="graph-layout">
      <GraphCanvas
        :nodes="nodes"
        :edges="edges"
        :selected-node-id="selectedNodeId"
        @select-node="selectedNodeId = $event"
      />

      <section class="shell-panel detail-panel">
        <div class="detail-head">
          <div>
            <p class="section-label">节点详情</p>
            <h3 class="detail-title">
              {{ selectedNode?.label || '选择一个节点查看关系' }}
            </h3>
          </div>
          <span class="badge badge-gray">{{ relatedEdges.length }} 条关系</span>
        </div>

        <p v-if="error" class="error-copy">{{ error }}</p>
        <p v-else-if="loading" class="detail-copy">图谱加载中...</p>
        <p v-else-if="!selectedNode" class="detail-copy">
          点击左侧节点胶囊后，这里会展示与该节点直接相关的关系边。
        </p>

        <div v-else class="relation-stack">
          <article
            v-for="edge in relatedEdges"
            :key="`${edge.from}-${edge.to}-${edge.label}-${edge.doc_id || ''}`"
            class="relation-card"
          >
            <strong>{{ edge.label }}</strong>
            <p>{{ describeEdge(edge) }}</p>
            <small v-if="edge.doc_id">来源：{{ edge.doc_id }}</small>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

import GraphCanvas from '@/components/GraphCanvas.vue'
import { api } from '@/api'

const nodes = ref([])
const edges = ref([])
const selectedNodeId = ref('')
const docFilter = ref('')
const loading = ref(false)
const error = ref('')

const selectedNode = computed(() => (
  nodes.value.find((node) => node.id === selectedNodeId.value) || null
))

const relatedEdges = computed(() => {
  if (!selectedNodeId.value) return []
  return edges.value.filter((edge) => (
    edge.from === selectedNodeId.value || edge.to === selectedNodeId.value
  ))
})

const findNodeLabel = (nodeId) => {
  const matched = nodes.value.find((node) => node.id === nodeId)
  return matched?.label || nodeId
}

const describeEdge = (edge) => (
  `${findNodeLabel(edge.from)} ${edge.label} ${findNodeLabel(edge.to)}`
)

const loadGraph = async () => {
  loading.value = true
  error.value = ''

  try {
    const params = docFilter.value ? { doc_ids: [docFilter.value] } : {}
    const response = await api.getGraph(params)
    nodes.value = response.data?.nodes || []
    edges.value = response.data?.edges || []
    selectedNodeId.value = nodes.value[0]?.id || ''
  } catch (graphError) {
    error.value = graphError.message || '图谱加载失败'
    nodes.value = []
    edges.value = []
    selectedNodeId.value = ''
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadGraph()
})
</script>

<style scoped lang="scss">
.graph-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.graph-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.16), transparent 34%),
    linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 56%, #ECFEFF 100%);
}

.hero-title {
  font-size: 28px;
  line-height: 1.2;
  color: var(--ink-strong);
  margin-top: 6px;
}

.hero-copy {
  margin-top: 10px;
  max-width: 640px;
  color: var(--ink-muted);
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-input {
  min-width: 280px;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  background: #fff;

  &:focus {
    outline: none;
    border-color: var(--blue-600);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }
}

.refresh-btn {
  border: none;
  background: var(--ink-strong);
  color: #fff;
  border-radius: 12px;
  padding: 12px 16px;
  font-weight: 600;
  cursor: pointer;
}

.graph-layout {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 20px;
  align-items: start;
}

.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 320px;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--ink-strong);
  margin-top: 4px;
}

.detail-copy {
  color: var(--ink-muted);
  line-height: 1.7;
}

.relation-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.relation-card {
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 16px;
  background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);

  strong {
    color: var(--ink-strong);
  }

  p {
    margin-top: 6px;
    color: var(--ink-body);
  }

  small {
    display: inline-block;
    margin-top: 8px;
    color: var(--ink-light);
  }
}

.error-copy {
  color: var(--red-600);
}

@media (max-width: 1024px) {
  .graph-hero,
  .graph-layout {
    display: grid;
    grid-template-columns: 1fr;
  }

  .filter-input {
    min-width: 0;
    width: 100%;
  }
}
</style>
