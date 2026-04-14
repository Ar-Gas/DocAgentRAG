<template>
  <section class="topic-tree shell-panel">
    <div class="panel-head">
      <h4>语义主题树</h4>
      <div class="tree-actions">
        <el-tag size="small" type="info">{{ tree?.total_documents || 0 }} 篇</el-tag>
        <el-button v-if="showRebuild" :loading="rebuilding" size="small" @click="emit('rebuild')">
          重建
        </el-button>
      </div>
    </div>

    <el-skeleton v-if="loading" animated :rows="8" />

    <template v-else-if="tree?.topics?.length">
      <article
        v-for="topic in tree.topics"
        :key="topic.topic_id"
        class="topic-card"
      >
        <!-- 主题头：标签 + 文档数，可折叠 -->
        <div class="topic-head" @click="toggleTopic(topic.topic_id)">
          <div class="topic-title">
            <h5>{{ topic.label }}</h5>
            <p>{{ topic.document_count }} 篇</p>
          </div>
          <span class="expand-arrow" :class="{ expanded: isTopicExpanded(topic.topic_id) }">▾</span>
        </div>

        <div v-if="isTopicExpanded(topic.topic_id)" class="child-topic-list">
          <article
            v-for="child in normalizedChildren(topic)"
            :key="child.topic_id"
            class="child-topic-card"
          >
            <div class="child-head" @click.stop="toggleChild(child.topic_id)">
              <div class="topic-title">
                <h5>{{ child.label }}</h5>
                <p>{{ child.document_count }} 篇</p>
              </div>
              <span class="expand-arrow" :class="{ expanded: isChildExpanded(child.topic_id) }">▾</span>
            </div>

            <div v-if="isChildExpanded(child.topic_id)" class="doc-name-list">
              <button
                v-for="document in (child.documents || [])"
                :key="document.document_id"
                type="button"
                class="doc-name-chip"
                :class="{ 'is-active': document.document_id === selectedDocumentId }"
                @click.stop="emit('select-document', document.document_id, null)"
                :title="document.filename"
              >
                <span class="doc-icon">{{ fileIcon(document.file_type) }}</span>
                <span class="doc-name">{{ document.filename }}</span>
              </button>
            </div>
          </article>
        </div>
      </article>
    </template>

    <el-empty v-else description="当前语料还没有生成动态主题树。" />
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  tree: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  rebuilding: { type: Boolean, default: false },
  selectedDocumentId: { type: String, default: '' },
  showRebuild: { type: Boolean, default: false },
})

const emit = defineEmits(['select-document', 'rebuild'])

const expandedTopics = ref(new Set())
const expandedChildren = ref(new Set())

const toggleTopic = (id) => {
  if (expandedTopics.value.has(id)) {
    expandedTopics.value = new Set([...expandedTopics.value].filter((x) => x !== id))
  } else {
    expandedTopics.value = new Set([...expandedTopics.value, id])
  }
}

const isTopicExpanded = (id) => expandedTopics.value.has(id)

const toggleChild = (id) => {
  if (expandedChildren.value.has(id)) {
    expandedChildren.value = new Set([...expandedChildren.value].filter((x) => x !== id))
  } else {
    expandedChildren.value = new Set([...expandedChildren.value, id])
  }
}

const isChildExpanded = (id) => expandedChildren.value.has(id)

const normalizedChildren = (topic) => {
  if (topic?.children?.length) {
    return topic.children
  }
  if (topic?.documents?.length) {
    return [{
      topic_id: `${topic.topic_id}-leaf`,
      label: topic.label,
      document_count: topic.document_count || topic.documents.length,
      documents: topic.documents,
    }]
  }
  return []
}

const fileIcon = (fileType) => {
  const t = (fileType || '').toLowerCase()
  if (t === '.pdf') return '📄'
  if (['.doc', '.docx'].includes(t)) return '📝'
  if (['.xls', '.xlsx'].includes(t)) return '📊'
  if (['.ppt', '.pptx'].includes(t)) return '📑'
  if (['.txt', '.md'].includes(t)) return '📃'
  return '📎'
}
</script>

<style scoped lang="scss">
.topic-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;

  h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--ink-strong);
  }
}

.tree-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.topic-card {
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  border: 1px solid var(--line);
  overflow: hidden;
}

.topic-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;

  &:hover { background: var(--bg-subtle); }
}

.topic-title {
  h5 {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-strong);
  }

  p {
    margin-top: 2px;
    font-size: 11px;
    color: var(--ink-muted);
  }
}

.expand-arrow {
  font-size: 14px;
  color: var(--ink-muted);
  transition: transform 0.2s;
  flex-shrink: 0;

  &.expanded { transform: rotate(180deg); }
}

.doc-name-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 8px 8px;
  border-top: 1px solid var(--line);
}

.child-topic-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  border-top: 1px solid var(--line);
}

.child-topic-card {
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.66);
  overflow: hidden;
}

.child-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  cursor: pointer;
  user-select: none;

  &:hover { background: var(--bg-subtle); }
}

.doc-name-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s;
  width: 100%;

  &:hover { background: var(--bg-subtle); }

  &.is-active {
    background: var(--blue-50);
    color: var(--blue-700);
  }
}

.doc-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.doc-name {
  font-size: 12px;
  color: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  color: var(--ink-body);
}

.doc-name-chip.is-active .doc-name {
  color: var(--blue-700);
  font-weight: 600;
}
</style>
