<template>
  <section class="shell-panel directory-search">
    <div class="search-copy">
      <h3>目录搜索</h3>
      <p>仅在当前目录内搜索文档，像文件夹检索一样直接。</p>
    </div>

    <div class="search-row">
      <el-input
        :model-value="query"
        :disabled="disabled || loading"
        clearable
        placeholder="输入文件名或关键词"
        @update:model-value="emit('update:query', $event)"
        @keyup.enter="handleSearch"
      />
      <el-button type="primary" :loading="loading" :disabled="!canSearch" @click="handleSearch">搜索</el-button>
      <el-button :disabled="!canReset" @click="emit('reset')">重置</el-button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  query: {
    type: String,
    default: '',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:query', 'search', 'reset'])
const canSearch = computed(() => !props.disabled && !props.loading)
const canReset = computed(() => !props.disabled && !props.loading && Boolean(props.query.trim()))

const handleSearch = () => {
  if (!canSearch.value) {
    return
  }
  emit('search')
}
</script>

<style scoped lang="scss">
.directory-search {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.search-copy {
  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--ink-strong);
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--ink-muted);
  }
}

.search-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 10px;
  align-items: center;
}

@media (max-width: 900px) {
  .search-row {
    grid-template-columns: 1fr;
  }
}
</style>
