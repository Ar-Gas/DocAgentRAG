<template>
  <div class="graph-page">
    <div class="graph-container">
      <div class="controls">
        <button @click="loadGraph">刷新图谱</button>
        <input
          v-model="searchEntity"
          type="text"
          placeholder="搜索实体..."
          @keyup.enter="searchEntity"
        />
      </div>

      <div id="graph" ref="graphContainer"></div>

      <!-- 节点信息 -->
      <div v-if="selectedNode" class="node-info">
        <h3>{{ selectedNode.label }}</h3>
        <p v-for="rel in nodeRelations" :key="rel">{{ rel }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useApi } from "@/api";

const api = useApi();

const graphContainer = ref(null);
const selectedNode = ref(null);
const nodeRelations = ref([]);
const searchEntity = ref("");
let network = null;

onMounted(async () => {
  loadGraph();
});

const loadGraph = async () => {
  try {
    const response = await fetch("/api/v1/topics/graph");
    const { data } = await response.json();

    // 转换数据格式适配 vis-network
    const nodes = data.nodes.map(n => ({
      id: n.id,
      label: n.label,
      title: n.title
    }));

    const edges = data.edges.map(e => ({
      from: e.from,
      to: e.to,
      label: e.label,
      arrows: "to"
    }));

    // 初始化 vis-network（需要在 HTML 中引入 vis-network.js）
    if (typeof vis !== "undefined") {
      const container = graphContainer.value;
      const graphData = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
      const options = {
        physics: {
          enabled: true,
          stabilization: { iterations: 200 }
        }
      };

      network = new vis.Network(container, graphData, options);

      network.on("selectNode", (event) => {
        const nodeId = event.nodes[0];
        selectedNode.value = nodes.find(n => n.id === nodeId);
        loadNodeInfo(nodeId);
      });
    }
  } catch (e) {
    console.error("加载图谱失败:", e);
  }
};

const loadNodeInfo = async (nodeId) => {
  try {
    const response = await fetch(`/api/v1/topics/${nodeId}/related`);
    const { data } = await response.json();
    nodeRelations.value = data.direct_relations.map(
      r => `${r.subject} ${r.predicate} ${r.object}`
    );
  } catch (e) {
    console.error("加载节点信息失败:", e);
  }
};
</script>

<style scoped>
.graph-page {
  padding: 20px;
}

.graph-container {
  display: flex;
  height: 800px;
  gap: 20px;
}

.controls {
  position: absolute;
  top: 20px;
  left: 20px;
  z-index: 10;
}

.controls button,
.controls input {
  padding: 8px 12px;
  margin-right: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

#graph {
  flex: 1;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.node-info {
  width: 300px;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #f9f9f9;
  overflow-y: auto;
}

.node-info h3 {
  margin-top: 0;
}

.node-info p {
  margin: 8px 0;
  font-size: 12px;
  color: #666;
}
</style>
