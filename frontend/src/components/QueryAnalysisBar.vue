<template>
  <div class="query-analysis-bar">
    <div class="analysis-content">
      <div class="section">
        <label>查询意图：</label>
        <span class="tag" :class="`intent-${analysis.intent}`">
          {{ intentLabel }}
        </span>
      </div>

      <div class="section">
        <label>扩展查询：</label>
        <div class="tags">
          <span
            v-for="q in analysis.expanded_queries"
            :key="q"
            class="tag expanded-query"
          >
            {{ q }}
          </span>
        </div>
      </div>

      <div v-if="analysis.entity_filters.length" class="section">
        <label>识别实体：</label>
        <div class="tags">
          <span
            v-for="e in analysis.entity_filters"
            :key="e"
            class="tag entity"
          >
            {{ e }}
          </span>
        </div>
      </div>

      <div v-if="analysis.doc_type_hint" class="section">
        <label>文档类型提示：</label>
        <span class="tag doc-type">{{ analysis.doc_type_hint }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  analysis: {
    type: Object,
    default: () => ({
      intent: "事实查找",
      expanded_queries: [],
      entity_filters: [],
      doc_type_hint: null
    })
  }
});

const intentLabel = computed(() => {
  const labels = {
    "事实查找": "📌 事实查找",
    "文档定位": "🔍 文档定位",
    "内容总结": "📄 内容总结",
    "比较分析": "⚖️ 比较分析"
  };
  return labels[props.analysis.intent] || props.analysis.intent;
});
</script>

<style scoped>
.query-analysis-bar {
  padding: 15px;
  background: #f0f5ff;
  border: 1px solid #d0e0ff;
  border-radius: 4px;
  margin-bottom: 20px;
}

.analysis-content {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
}

.section {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section label {
  font-weight: bold;
  color: #333;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  white-space: nowrap;
}

.intent-事实查找 {
  background: #e3f2fd;
  color: #1976d2;
}

.intent-文档定位 {
  background: #f3e5f5;
  color: #7b1fa2;
}

.intent-内容总结 {
  background: #e8f5e9;
  color: #388e3c;
}

.intent-比较分析 {
  background: #fff3e0;
  color: #f57c00;
}

.expanded-query {
  background: #e0f2f1;
  color: #00897b;
}

.entity {
  background: #fce4ec;
  color: #c2185b;
}

.doc-type {
  background: #fff9c4;
  color: #f57f17;
}
</style>
