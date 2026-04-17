<template>
  <div class="qa-page">
    <div class="qa-container">
      <!-- 选择文档 -->
      <div class="select-docs">
        <label>选择文档范围：</label>
        <select v-model="selectedDocs" multiple size="5">
          <option v-for="doc in allDocs" :key="doc.id" :value="doc.id">
            {{ doc.filename }}
          </option>
        </select>
        <button @click="clearSelection">清空选择</button>
        <p v-if="selectedDocs.length" class="selected-count">
          已选择 {{ selectedDocs.length }} 个文档
        </p>
      </div>

      <!-- 问题输入 -->
      <div class="qa-input">
        <textarea
          v-model="query"
          placeholder="输入你的问题，例如：这些文档对数据增强有什么不同观点？"
          rows="3"
        ></textarea>
        <button @click="submitQuery" :disabled="!query || loading">
          {{ loading ? "加载中..." : "提问" }}
        </button>
      </div>

      <!-- 答案显示（流式） -->
      <div v-if="answer" class="qa-answer">
        <h3>回答：</h3>
        <div class="answer-content">{{ answer }}</div>

        <!-- 引用 -->
        <div v-if="citations.length" class="citations">
          <h4>引用来源：</h4>
          <ul>
            <li v-for="(cite, idx) in citations" :key="idx">
              <a :href="`#doc-${cite.doc_id}`">{{ cite.doc_id }}</a>
              <span v-if="cite.section">§{{ cite.section }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- 错误提示 -->
      <div v-if="error" class="error">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useApi } from "@/api";

const api = useApi();

const query = ref("");
const selectedDocs = ref([]);
const allDocs = ref([]);
const answer = ref("");
const citations = ref([]);
const loading = ref(false);
const error = ref("");

onMounted(async () => {
  // 获取所有文档
  const res = await api.getDocuments();
  allDocs.value = res.data.items || [];
});

const submitQuery = async () => {
  if (!query.value.trim()) return;

  loading.value = true;
  error.value = "";
  answer.value = "";
  citations.value = [];

  try {
    const response = await fetch("/api/v1/qa/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query.value,
        doc_ids: selectedDocs.value.length ? selectedDocs.value : null
      })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = JSON.parse(line.slice(6));
          if (data.chunk) {
            answer.value += data.chunk;
          }
          if (data.status === "complete") {
            // 解析引用
            citations.value = extractCitations(answer.value);
          }
          if (data.error) {
            error.value = data.error;
          }
        }
      }
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
};

const extractCitations = (text) => {
  const pattern = /\[([^\[\]]+?)(?:\s+§([^\[\]]+?))?\]/g;
  const citations = [];
  const seen = new Set();

  let match;
  while ((match = pattern.exec(text)) !== null) {
    const key = `${match[1]}_${match[2] || ""}`;
    if (!seen.has(key)) {
      citations.push({
        doc_id: match[1].trim(),
        section: match[2] ? match[2].trim() : ""
      });
      seen.add(key);
    }
  }

  return citations;
};

const clearSelection = () => {
  selectedDocs.value = [];
};
</script>

<style scoped>
.qa-page {
  padding: 20px;
}

.qa-container {
  max-width: 1000px;
  margin: 0 auto;
}

.select-docs {
  margin-bottom: 20px;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.select-docs select {
  width: 100%;
  padding: 8px;
  margin: 10px 0;
}

.selected-count {
  color: #666;
  font-size: 12px;
}

.qa-input {
  margin-bottom: 20px;
}

.qa-input textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-family: Arial, sans-serif;
}

.qa-input button {
  margin-top: 10px;
  padding: 10px 20px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.qa-input button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.qa-answer {
  padding: 15px;
  background: #f9f9f9;
  border-radius: 4px;
}

.answer-content {
  margin: 10px 0;
  line-height: 1.6;
  white-space: pre-wrap;
}

.citations {
  margin-top: 20px;
  padding-top: 10px;
  border-top: 1px solid #ddd;
}

.error {
  color: red;
  padding: 10px;
  background: #ffe6e6;
  border-radius: 4px;
}
</style>
