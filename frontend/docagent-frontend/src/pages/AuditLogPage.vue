<template>
  <section class="audit-page">
    <div class="page-header shell-panel">
      <div>
        <h3>审计日志</h3>
        <p>按用户、动作和结果回看文档系统关键操作，满足日常追踪和审计留痕。</p>
      </div>
      <button type="button" class="ghost-button" :disabled="loading" @click="loadLogs">
        {{ loading ? '加载中…' : '刷新日志' }}
      </button>
    </div>

    <div class="shell-panel panel-stack">
      <form class="filter-grid" @submit.prevent="loadLogs">
        <label>
          <span>动作</span>
          <input v-model.trim="filters.action_type" type="text" placeholder="例如 upload_document" />
        </label>
        <label>
          <span>目标类型</span>
          <input v-model.trim="filters.target_type" type="text" placeholder="例如 document" />
        </label>
        <label>
          <span>执行结果</span>
          <select v-model="filters.result">
            <option value="">全部</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
          </select>
        </label>
        <label>
          <span>操作人</span>
          <input v-model.trim="filters.username" type="text" placeholder="按用户名筛选" />
        </label>
      </form>

      <div class="panel-actions">
        <button type="button" class="primary-button" :disabled="loading" @click="loadLogs">应用筛选</button>
      </div>

      <div v-if="loading" class="empty-copy">正在加载审计日志…</div>
      <div v-else-if="logs.length" class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>用户</th>
              <th>动作</th>
              <th>目标</th>
              <th>结果</th>
              <th>附加信息</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>{{ formatTime(log.created_at) }}</td>
              <td>{{ log.username_snapshot || log.user_id || '-' }}</td>
              <td>{{ log.action_type }}</td>
              <td>{{ `${log.target_type || '-'} / ${log.target_id || '-'}` }}</td>
              <td>{{ log.result === 'success' ? '成功' : '失败' }}</td>
              <td class="metadata-cell">{{ formatMetadata(log.metadata_json) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-copy">当前筛选条件下没有审计日志。</div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'

import { api } from '@/api'

const logs = ref([])
const loading = ref(false)

const filters = reactive({
  action_type: '',
  target_type: '',
  result: '',
  username: '',
})

const loadLogs = async () => {
  loading.value = true
  try {
    const response = await api.getAuditLogs({
      page: 1,
      page_size: 50,
      action_type: filters.action_type || undefined,
      target_type: filters.target_type || undefined,
      result: filters.result || undefined,
      username: filters.username || undefined,
    })
    logs.value = response.data?.items || []
  } finally {
    loading.value = false
  }
}

const formatTime = (value) => {
  if (!value) {
    return '-'
  }

  return String(value).replace('T', ' ').slice(0, 19)
}

const formatMetadata = (value) => {
  if (!value || typeof value !== 'object' || !Object.keys(value).length) {
    return '-'
  }
  return Object.entries(value)
    .map(([key, item]) => `${key}: ${item}`)
    .join(' | ')
}

onMounted(() => {
  loadLogs()
})
</script>

<style scoped lang="scss">
.audit-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;

  h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--ink-strong);
    margin-bottom: 4px;
  }

  p {
    font-size: 13px;
    line-height: 1.6;
    color: var(--ink-muted);
  }
}

.panel-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;

  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  span {
    font-size: 12px;
    color: var(--ink-muted);
  }

  input,
  select {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    font-size: 13px;
    color: var(--ink-strong);
    background: #fff;
  }
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
}

.ghost-button,
.primary-button {
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.ghost-button {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink-strong);
}

.primary-button {
  border: 1px solid #1D4ED8;
  background: #1D4ED8;
  color: #fff;
}

.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;

  th,
  td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: top;
  }

  thead th {
    font-size: 12px;
    color: var(--ink-muted);
    font-weight: 600;
    background: var(--bg-subtle);
  }
}

.metadata-cell {
  min-width: 240px;
  color: var(--ink-muted);
}

.empty-copy {
  padding: 20px;
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  border: 1px dashed var(--line);
  color: var(--ink-muted);
  font-size: 13px;
}

@media (max-width: 1080px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }

  .filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
