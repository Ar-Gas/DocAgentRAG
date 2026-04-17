<template>
  <section class="shell-panel graph-canvas">
    <div class="canvas-head">
      <div>
        <p class="section-label">图谱快照</p>
        <h3 class="canvas-title">实体网络</h3>
      </div>
      <div class="canvas-metrics">
        <span class="badge badge-gray">{{ nodes.length }} 个节点</span>
        <span class="badge badge-gray">{{ edges.length }} 条关系</span>
      </div>
    </div>

    <div v-if="!nodes.length" class="canvas-empty">
      暂无图谱数据，请调整筛选条件后重试。
    </div>

    <div v-else class="canvas-body">
      <div class="node-cloud">
        <button
          v-for="node in nodes"
          :key="node.id"
          type="button"
          class="node-pill"
          :class="{ 'node-pill--active': node.id === selectedNodeId }"
          @click="$emit('select-node', node.id)"
        >
          <span>{{ node.label }}</span>
          <small>{{ node.degree || 0 }}</small>
        </button>
      </div>

      <div class="edge-list">
        <article
          v-for="edge in edges"
          :key="`${edge.from}-${edge.to}-${edge.label}`"
          class="edge-card"
        >
          <div class="edge-main">
            <strong>{{ findNodeLabel(edge.from) }}</strong>
            <span class="edge-arrow">{{ edge.label }}</span>
            <strong>{{ findNodeLabel(edge.to) }}</strong>
          </div>
          <p v-if="edge.doc_id" class="edge-doc">来源文档：{{ edge.doc_id }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
const props = defineProps({
  nodes: {
    type: Array,
    default: () => [],
  },
  edges: {
    type: Array,
    default: () => [],
  },
  selectedNodeId: {
    type: String,
    default: '',
  },
})

defineEmits(['select-node'])

const findNodeLabel = (nodeId) => {
  const matched = props.nodes.find((node) => node.id === nodeId)
  return matched?.label || nodeId
}
</script>

<style scoped lang="scss">
.graph-canvas {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.canvas-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.canvas-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--ink-strong);
  margin-top: 4px;
}

.canvas-metrics {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.canvas-empty {
  min-height: 220px;
  border: 1px dashed var(--line-strong);
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: var(--ink-muted);
}

.canvas-body {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 18px;
}

.node-cloud {
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 16px;
  background: linear-gradient(180deg, #F8FAFC 0%, #EEF2FF 100%);
  min-height: 220px;
}

.node-pill {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink-body);
  border-radius: 999px;
  padding: 10px 12px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;

  small {
    color: var(--ink-light);
  }

  &--active {
    border-color: var(--blue-600);
    color: var(--blue-700);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }
}

.edge-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.edge-card {
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 16px;
  background: #fff;
}

.edge-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--ink-strong);
}

.edge-arrow {
  color: var(--blue-700);
  background: var(--blue-50);
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 600;
}

.edge-doc {
  margin-top: 8px;
  font-size: 12px;
  color: var(--ink-muted);
}

@media (max-width: 900px) {
  .canvas-body {
    grid-template-columns: 1fr;
  }
}
</style>
