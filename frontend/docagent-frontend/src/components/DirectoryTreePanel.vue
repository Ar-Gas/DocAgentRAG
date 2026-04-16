<template>
  <section class="shell-panel tree-panel">
    <div class="panel-head">
      <h4>目录树</h4>
    </div>

    <ul v-if="flatNodes.length" class="tree-list">
      <li v-for="entry in flatNodes" :key="entry.node.node_id">
        <button
          type="button"
          class="tree-node"
          :class="{
            'is-active': nodeScopeKey(entry.node) === activeScopeKey,
            'is-locked': !isSelectable(entry.node),
          }"
          :style="{ paddingLeft: `${12 + entry.depth * 16}px` }"
          :disabled="!isSelectable(entry.node)"
          @click="handleNodeClick(entry.node)"
        >
          <span class="node-label">{{ entry.node.label }}</span>
          <span v-if="entry.node.locked || entry.node.accessible === false" class="lock-tag">锁定</span>
        </button>
      </li>
    </ul>

    <el-empty v-else description="暂无目录结构" />
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodes: {
    type: Array,
    default: () => [],
  },
  activeScopeKey: {
    type: String,
    default: 'root',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select-scope'])

const flattenNodes = (items = [], depth = 0, result = []) => {
  items.forEach((node) => {
    result.push({ node, depth })
    if (Array.isArray(node.children) && node.children.length) {
      flattenNodes(node.children, depth + 1, result)
    }
  })
  return result
}

const flatNodes = computed(() => flattenNodes(props.nodes))

const isSelectable = (node) => !props.disabled && !(node?.locked || node?.accessible === false)

const nodeScopeKey = (node) => {
  if (!node?.visibility_scope) {
    return 'root'
  }

  const keys = [node.visibility_scope]
  if (node.department_id) {
    keys.push(node.department_id)
  }
  if (node.business_category_id) {
    keys.push(node.business_category_id)
  }
  return keys.join(':')
}

const handleNodeClick = (node) => {
  if (!isSelectable(node)) {
    return
  }
  emit('select-scope', {
    visibility_scope: node.visibility_scope || null,
    department_id: node.department_id || null,
    business_category_id: node.business_category_id || null,
  })
}
</script>

<style scoped lang="scss">
.tree-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 480px;
}

.panel-head h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
}

.tree-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tree-node {
  width: 100%;
  min-height: 36px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-body);
  text-align: left;
  cursor: pointer;
  transition: 0.12s background, 0.12s border-color, 0.12s color;

  &:hover {
    background: var(--bg-subtle);
    border-color: var(--line);
  }

  &.is-active {
    color: var(--blue-700);
    background: var(--blue-50);
    border-color: var(--blue-200);
  }

  &.is-locked {
    color: var(--ink-muted);
    cursor: not-allowed;
  }
}

.node-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lock-tag {
  font-size: 11px;
  color: var(--amber-700);
  background: var(--amber-50);
  border: 1px solid var(--amber-200);
  border-radius: 999px;
  padding: 1px 8px;
  flex-shrink: 0;
}
</style>
