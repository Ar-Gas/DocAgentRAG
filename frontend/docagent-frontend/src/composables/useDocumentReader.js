import { ref } from 'vue'
import { api } from '@/api'

export function useDocumentReader() {
  const readerData = ref(null)
  const currentDocId = ref(null)
  const isLoading = ref(false)

  async function loadReader(docId, query = '', anchorBlockId = null) {
    if (!docId) return
    isLoading.value = true
    currentDocId.value = docId
    try {
      const response = await api.getDocumentReader(docId, query, anchorBlockId)
      readerData.value = response?.data ?? response ?? null
    } catch (err) {
      console.error('DocumentReader load error:', err)
      readerData.value = null
    } finally {
      isLoading.value = false
    }
  }

  function clearReader() {
    readerData.value = null
    currentDocId.value = null
  }

  return { readerData, currentDocId, isLoading, loadReader, clearReader }
}
