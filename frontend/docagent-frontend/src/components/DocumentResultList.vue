<template>
  <section class="result-list shell-panel">
    <div class="panel-head">
      <h4>命中文档</h4>
      <div class="head-metrics">
        <span>{{ documents.length }} 篇</span>
      </div>
    </div>

    <el-skeleton v-if="loading" animated :rows="6" />

    <template v-else-if="documents.length">
      <div
        v-for="document in documents"
        :key="document.document_id"
        class="result-card"
        :class="{ 'is-active': document.document_id === selectedDocumentId }"
      >
        <!-- 文档头部：始终可见，点击展开/收起 -->
        <div class="card-head" @click="toggleDocument(document)">
          <div class="card-title">
            <span
              class="filename"
              :class="{ 'is-disabled': document.file_available === false }"
              @click.stop="document.file_available !== false && emit('open-viewer', document)"
            >
              {{ document.filename }}
            </span>
            <span class="classification">{{ document.classification_result || '未分类' }}</span>
          </div>
          <div class="card-right">
            <div class="card-badges">
              <span class="score-chip">{{ toPercent(document.score || document.best_similarity) }}</span>
              <el-tag size="small" type="info">{{ document.file_type || '?' }}</el-tag>
              <el-tag size="small" type="success">命中 {{ document.hit_count || document.result_count || 0 }}</el-tag>
            </div>
            <span class="expand-arrow" :class="{ expanded: isExpanded(document.document_id) }">▾</span>
          </div>
        </div>

        <!-- 展开区域：去重证据块 + 操作按钮 -->
        <div v-if="isExpanded(document.document_id)" class="card-body">
          <!-- 匹配词标签 -->
          <div v-if="(document.matched_terms || []).length" class="term-row">
            <el-tag
              v-for="term in (document.matched_terms || []).slice(0, 4)"
              :key="`${document.document_id}-${term}`"
              size="small"
              type="warning"
            >
              {{ term }}
            </el-tag>
          </div>

          <div v-if="document.file_available === false" class="file-warning">
            原文件不存在或路径失效，当前仅支持查看已提取文本。
          </div>

          <!-- 去重后的证据块 -->
          <div class="evidence-list">
            <div
              v-for="(block, idx) in deduplicatedBlocks(document)"
              :key="block.block_id || idx"
              class="evidence-block"
              @click.stop="emit('select-document', document.document_id, block.block_id)"
            >
              <span class="block-label">段落 {{ (block.block_index || 0) + 1 }}</span>
              <div
                v-if="(block.heading_path || []).length || block.page_number || block.block_type"
                class="block-meta"
              >
                <span v-if="(block.heading_path || []).length">{{ block.heading_path.join(' > ') }}</span>
                <span v-if="block.page_number">第 {{ block.page_number }} 页</span>
                <span v-if="block.block_type">{{ block.block_type }}</span>
              </div>
              <p class="block-snippet">
                <template v-for="seg in highlightSnippet(block.snippet, query)" :key="seg.key">
                  <mark v-if="seg.highlight">{{ seg.text }}</mark>
                  <span v-else>{{ seg.text }}</span>
                </template>
              </p>
            </div>
          </div>

          <!-- 操作按钮行 -->
          <div class="card-actions">
            <button
              type="button"
              class="action-btn primary-btn"
              @click.stop="emit('select-document', document.document_id, document.best_block_id)"
            >
              阅读全文
            </button>
            <button
              type="button"
              class="action-btn"
              :disabled="document.file_available === false"
              @click.stop="emit('open-viewer', document)"
            >
              原文预览
            </button>
          </div>
        </div>
      </div>
    </template>

    <el-empty v-else description="输入检索词后，这里只显示文档，不再直接暴露分片。" />
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { buildSegmentsFromQuery } from '@/utils/highlight'

const props = defineProps({
  loading: { type: Boolean, default: false },
  documents: { type: Array, default: () => [] },
  query: { type: String, default: '' },
  selectedDocumentId: { type: String, default: '' },
})

const emit = defineEmits(['select-document', 'open-viewer'])

const expandedIds = ref(new Set())

const toggleDocument = (document) => {
  const id = document.document_id
  if (expandedIds.value.has(id)) {
    expandedIds.value = new Set([...expandedIds.value].filter((x) => x !== id))
  } else {
    expandedIds.value = new Set([...expandedIds.value, id])
    emit('select-document', id, document.best_block_id || null)
  }
}

const isExpanded = (id) => expandedIds.value.has(id)

// 外部选中时自动展开（例如主题树点击）
watch(
  () => props.selectedDocumentId,
  (id) => {
    if (id && !expandedIds.value.has(id)) {
      expandedIds.value = new Set([...expandedIds.value, id])
    }
  },
  { immediate: true },
)

const toPercent = (value) => `${((value || 0) * 100).toFixed(1)}%`

// 先按 block_id 去重，再按内容前 80 字符去重
const deduplicatedBlocks = (document) => {
  const blocks = document.evidence_blocks || []
  const seenIds = new Set()
  const seenSnippets = new Set()
  return blocks.filter((block) => {
    const id = block.block_id || ''
    const snip = (block.snippet || '').slice(0, 80)
    if (id && seenIds.has(id)) return false
    if (snip && seenSnippets.has(snip)) return false
    if (id) seenIds.add(id)
    if (snip) seenSnippets.add(snip)
    return true
  })
}

const highlightSnippet = (text, query) =>
  buildSegmentsFromQuery(text || '', query || '')
</script>

<style scoped lang="scss">
.result-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;

  h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--ink-strong);
  }
}

.head-metrics {
  font-size: 12px;
  color: var(--ink-muted);
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  padding: 3px 10px;
  border-radius: 999px;
}

.result-card {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: hidden;

  &:hover { border-color: var(--blue-400); }

  &.is-active {
    border-color: var(--blue-600);
    box-shadow: 0 0 0 3px var(--blue-100);
  }
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  cursor: pointer;
  user-select: none;

  &:hover { background: var(--bg-subtle); }
}

.card-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--blue-600);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  &:hover { text-decoration: underline; }

  &.is-disabled {
    color: var(--ink-muted);
    cursor: not-allowed;
    &:hover { text-decoration: none; }
  }
}

.classification {
  font-size: 11px;
  color: var(--ink-muted);
}

.card-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.card-badges {
  display: flex;
  gap: 5px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.score-chip {
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  color: var(--blue-700);
  background: var(--blue-100);
  font-size: 11px;
  font-weight: 700;
}

.file-warning {
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  line-height: 1.5;
}

.expand-arrow {
  font-size: 14px;
  color: var(--ink-muted);
  transition: transform 0.2s;
  line-height: 1;

  &.expanded { transform: rotate(180deg); }
}

.card-body {
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-top: 1px solid var(--line);
}

.term-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.evidence-block {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  border: 1px solid var(--line);
  cursor: pointer;
  transition: border-color 0.12s;

  &:hover { border-color: var(--blue-400); }
}

.block-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 4px 0 6px;
  font-size: 11px;
  color: var(--ink-muted);
}

.block-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-muted);
  margin-bottom: 4px;
}

.block-snippet {
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-body);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.card-actions {
  display: flex;
  gap: 8px;
  padding-top: 2px;
}

.action-btn {
  flex: 1;
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
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

  &:disabled {
    cursor: not-allowed;
    opacity: 0.6;
    border-color: var(--line);
    color: var(--ink-muted);
    background: var(--bg-subtle);
  }

  &.primary-btn {
    background: var(--blue-600);
    color: #fff;
    border-color: var(--blue-600);

    &:hover {
      background: var(--blue-700);
      border-color: var(--blue-700);
      color: #fff;
    }
  }
}

mark {
  background: #fef08a;
  color: #713f12;
  border-radius: 3px;
  padding: 0 2px;
}
</style>
