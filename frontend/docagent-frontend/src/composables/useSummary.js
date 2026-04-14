import { ref } from 'vue'
import { api } from '@/api'

export function useSummary() {
  const summary = ref(null)
  const classificationReport = ref(null)
  const summaryVisible = ref(false)
  const classificationVisible = ref(false)
  const summaryLoading = ref(false)
  const classificationLoading = ref(false)

  async function openSummary(query, documents) {
    if (!documents?.length) return
    summaryVisible.value = true
    summaryLoading.value = true
    try {
      const response = await api.summarizeResults(query, documents.slice(0, 12))
      summary.value = response?.data ?? response ?? null
    } finally {
      summaryLoading.value = false
    }
  }

  async function openClassificationReport(query, documents) {
    if (!documents?.length) return
    classificationVisible.value = true
    classificationLoading.value = true
    try {
      const response = await api.generateClassificationTable(query, documents.slice(0, 20), true)
      classificationReport.value = response?.data ?? response ?? null
    } finally {
      classificationLoading.value = false
    }
  }

  return {
    summary,
    classificationReport,
    summaryVisible,
    classificationVisible,
    summaryLoading,
    classificationLoading,
    openSummary,
    openClassificationReport,
  }
}
