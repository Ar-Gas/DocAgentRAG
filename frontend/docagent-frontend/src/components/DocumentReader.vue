<template>
  <section class="reader-panel shell-panel">
    <div class="panel-head">
      <h4>文本阅读区</h4>
      <div class="reader-nav" v-if="flatMatches.length">
        <button type="button" class="nav-button" @click="moveCursor(-1)">上一处</button>
        <span class="nav-count">{{ activeDisplayIndex }} / {{ flatMatches.length }}</span>
        <button type="button" class="nav-button" @click="moveCursor(1)">下一处</button>
      </div>
    </div>

    <el-skeleton v-if="loading" animated :rows="10" />

    <template v-else-if="reader">
      <div class="reader-meta">
        <div>
          <h5>{{ reader.filename }}</h5>
          <p>
            归属部门：{{ reader.owner_department_name || reader.owner_department_id || '未归属' }}
            · 业务分类：{{ reader.business_category_name || reader.business_category_id || '待整理' }}
          </p>
        </div>
        <div class="meta-tags">
          <el-tag size="small" type="info">{{ reader.file_type || '未知类型' }}</el-tag>
          <el-tag size="small" type="success">{{ reader.total_matches || 0 }} 处命中</el-tag>
        </div>
      </div>

      <div class="reader-surface">
        <article
          v-for="block in reader.blocks || []"
          :key="block.block_id"
          :ref="(element) => setBlockRef(block.block_id, element)"
          class="reader-block"
        >
          <header>
            <span>段落 {{ (block.block_index || 0) + 1 }}</span>
            <span>{{ block.block_type || 'paragraph' }}</span>
            <span v-if="(block.heading_path || []).length">{{ block.heading_path.join(' > ') }}</span>
            <span v-if="block.page_number">第 {{ block.page_number }} 页</span>
          </header>
          <p>
            <template v-for="segment in buildBlockSegments(block)" :key="segment.key">
              <mark v-if="segment.highlight" :class="{ 'is-active': segment.active }">{{ segment.text }}</mark>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
        </article>
      </div>
    </template>

    <el-empty v-else description="选择文档后，这里会像 Ctrl+F 一样提供命中高亮与跳转。" />
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { buildSegmentsFromRanges } from '@/utils/highlight'

const props = defineProps({
  reader: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const blockRefs = ref({})
const activeCursor = ref(0)

// 5.6 组件卸载时清理 blockRefs，防止内存泄漏
onBeforeUnmount(() => {
  blockRefs.value = {}
})

const flatMatches = computed(() => {
  const flattened = []
  ;(props.reader?.blocks || []).forEach((block) => {
    ;(block.matches || []).forEach((match, matchIndex) => {
      flattened.push({
        ...match,
        key: `${block.block_id}-${matchIndex}-${match.start}-${match.end}`,
        block_id: block.block_id,
        block_index: block.block_index,
        match_index: matchIndex
      })
    })
  })
  return flattened
})

const activeMatch = computed(() => flatMatches.value[activeCursor.value] || null)
const activeDisplayIndex = computed(() => (flatMatches.value.length ? activeCursor.value + 1 : 0))

const syncCursorWithAnchor = async () => {
  const bestAnchor = props.reader?.best_anchor
  if (!flatMatches.value.length) {
    activeCursor.value = 0
    return
  }

  const anchorIndex = flatMatches.value.findIndex(
    (item) =>
      item.block_id === bestAnchor?.block_id &&
      item.match_index === (bestAnchor?.match_index ?? 0)
  )

  activeCursor.value = anchorIndex >= 0 ? anchorIndex : 0
  await nextTick()
  scrollToActiveMatch()
}

watch(() => props.reader, syncCursorWithAnchor, { immediate: true, deep: true })

const setBlockRef = (blockId, element) => {
  if (!blockId) {
    return
  }
  blockRefs.value[blockId] = element
}

const scrollToActiveMatch = () => {
  const blockId = activeMatch.value?.block_id
  if (!blockId) {
    return
  }
  blockRefs.value[blockId]?.scrollIntoView?.({
    block: 'center',
    behavior: 'smooth'
  })
}

const moveCursor = async (delta) => {
  if (!flatMatches.value.length) {
    return
  }

  activeCursor.value = (activeCursor.value + delta + flatMatches.value.length) % flatMatches.value.length
  await nextTick()
  scrollToActiveMatch()
}

const buildBlockSegments = (block) => {
  const ranges = (block.matches || []).map((match, matchIndex) => ({
    ...match,
    key: `${block.block_id}-${matchIndex}-${match.start}-${match.end}`
  }))

  return buildSegmentsFromRanges(block.text || '', ranges, (range) => range.key === activeMatch.value?.key)
}
</script>

<style scoped lang="scss">
.reader-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 100%;
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

.reader-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-count {
  min-width: 48px;
  text-align: center;
  font-size: 12px;
  color: var(--ink-muted);
  font-weight: 500;
}

.nav-button {
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  color: var(--ink-body);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;

  &:hover {
    border-color: var(--blue-600);
    color: var(--blue-600);
    background: var(--blue-50);
  }
}

.reader-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  border: 1px solid var(--line);

  h5 {
    font-size: 13px;
    font-weight: 600;
    color: var(--ink-strong);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  p {
    margin-top: 3px;
    font-size: 12px;
    color: var(--ink-muted);
  }
}

.meta-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
  flex-shrink: 0;
}

.reader-surface {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 800px;
  overflow: auto;
  padding-right: 4px;
}

.reader-block {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  border: 1px solid var(--line);

  header {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
    color: var(--ink-muted);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  p {
    line-height: 1.85;
    white-space: pre-wrap;
    color: var(--ink-body);
    font-size: 13px;
  }
}

mark {
  background: #FEF08A;
  color: #713F12;
  border-radius: 3px;
  padding: 0 2px;

  &.is-active {
    background: #FCD34D;
    box-shadow: 0 0 0 2px rgba(251, 191, 36, 0.4);
  }
}

@media (max-width: 860px) {
  .panel-head,
  .reader-meta {
    flex-direction: column;
    align-items: flex-start;
  }

  .reader-nav {
    width: 100%;
  }
}
</style>
