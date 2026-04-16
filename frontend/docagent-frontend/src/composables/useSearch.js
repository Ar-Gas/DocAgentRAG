import { ref, reactive } from 'vue'
import { api, workspaceSearchStream } from '@/api'

const createDefaultFilters = () => ({
  query: '',
  mode: 'hybrid',
  limit: 12,
  alpha: 0.5,
  use_rerank: false,
  use_query_expansion: true,
  use_llm_rerank: true,
  expansion_method: 'llm',
  file_types: [],
  filename: '',
  classification: '',
  date_range: [],
})

const emptyWorkspace = () => ({
  results: [],
  documents: [],
  total_results: 0,
  total_documents: 0,
  applied_filters: {},
})

export function useSearch() {
  const workspace = ref(emptyWorkspace())
  const filters = reactive(createDefaultFilters())
  const isLoading = ref(false)
  const isReranking = ref(false)

  let _cancelStream = null

  const buildSearchRequest = () => ({
    query: (filters.query ?? '').trim(),
    mode: filters.mode,
    limit: filters.limit,
    alpha: filters.alpha,
    use_rerank: filters.use_rerank,
    use_query_expansion: filters.use_query_expansion,
    use_llm_rerank: filters.use_llm_rerank,
    expansion_method: filters.expansion_method,
    file_types: filters.file_types || [],
    filename: filters.filename?.trim() || null,
    classification: filters.classification || null,
    date_from: filters.date_range?.[0] || null,
    date_to: filters.date_range?.[1] || null,
    group_by_document: true,
  })

  /**
   * 执行检索。
   * smart 模式走 SSE，其他模式走同步接口。
   * @param {Function} onFirstResult - 第一批结果回来时的回调（用于自动选中第一个文档）
   */
  async function executeSearch(onFirstResult) {
    // 取消上一次 SSE
    if (_cancelStream) { _cancelStream(); _cancelStream = null }

    isLoading.value = true
    isReranking.value = false
    workspace.value = emptyWorkspace()

    const req = buildSearchRequest()

    if (req.mode === 'smart') {
      _cancelStream = workspaceSearchStream(req, {
        onResults(data) {
          isLoading.value = false
          isReranking.value = true
          workspace.value = data?.data ?? data ?? emptyWorkspace()
          onFirstResult?.(workspace.value)
        },
        onReranked(data) {
          isReranking.value = false
          workspace.value = data?.data ?? data ?? workspace.value
          onFirstResult?.(workspace.value)
        },
        onDone() {
          isLoading.value = false
          isReranking.value = false
        },
        onError(err) {
          isLoading.value = false
          isReranking.value = false
          console.error('Smart search SSE error:', err)
        },
      })
      return
    }

    try {
      const response = await api.workspaceSearch(req)
      workspace.value = response?.data ?? response ?? emptyWorkspace()
      onFirstResult?.(workspace.value)
    } finally {
      isLoading.value = false
    }
  }

  function resetSearch() {
    if (_cancelStream) { _cancelStream(); _cancelStream = null }
    Object.assign(filters, createDefaultFilters())
    workspace.value = emptyWorkspace()
    isLoading.value = false
    isReranking.value = false
  }

  return {
    workspace,
    filters,
    isLoading,
    isReranking,
    buildSearchRequest,
    executeSearch,
    resetSearch,
  }
}
