<template>
  <section class="dashboard">
    <!-- 顶部指标 -->
    <div class="metrics-row">
      <article class="metric-card shell-panel">
        <div class="metric-icon metric-icon--blue">
          <el-icon><Document /></el-icon>
        </div>
        <div>
          <p class="metric-label">文档总数</p>
          <strong class="metric-value">{{ totalDocuments }}</strong>
        </div>
      </article>
      <article class="metric-card shell-panel">
        <div class="metric-icon metric-icon--green">
          <el-icon><Folder /></el-icon>
        </div>
        <div>
          <p class="metric-label">已分类</p>
          <strong class="metric-value">{{ classifiedCount }}</strong>
        </div>
      </article>
      <article class="metric-card shell-panel">
        <div class="metric-icon metric-icon--amber">
          <el-icon><DataBoard /></el-icon>
        </div>
        <div>
          <p class="metric-label">向量分片</p>
          <strong class="metric-value">{{ stats.total_chunks || 0 }}</strong>
        </div>
      </article>
      <article class="metric-card shell-panel">
        <div class="metric-icon metric-icon--purple">
          <el-icon><Grid /></el-icon>
        </div>
        <div>
          <p class="metric-label">文件类型</p>
          <strong class="metric-value">{{ Object.keys(stats.file_types || {}).length }}</strong>
        </div>
      </article>
    </div>

    <!-- 主内容 -->
    <div class="main-grid">
      <!-- 近期文档 -->
      <section class="shell-panel">
        <div class="section-head">
          <h3 class="section-title">最近入库</h3>
          <RouterLink to="/documents" class="link-more">查看全部 →</RouterLink>
        </div>
        <el-table :data="recentDocs.slice(0, 8)" :show-header="true">
          <el-table-column prop="filename" label="文件名" min-width="220">
            <template #default="{ row }">
              <div class="file-cell clickable" @click="openViewer(row)">
                <span class="file-type-dot" :class="`dot-${row.file_type?.replace('.','')}`"></span>
                <span class="filename-text">{{ row.filename }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="file_type" label="类型" width="80">
            <template #default="{ row }">
              <span class="badge badge-gray">{{ row.file_type }}</span>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="150">
            <template #default="{ row }">
              <span v-if="row.classification_result" class="badge badge-blue">{{ row.classification_result }}</span>
              <span v-else class="badge badge-amber">待分类</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at_iso" label="上传时间" width="160">
            <template #default="{ row }">
              <span class="text-muted">{{ formatDate(row.created_at_iso) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 右侧 -->
      <div class="side-col">
        <!-- 文件类型分布 -->
        <section class="shell-panel">
          <div class="section-head">
            <h3 class="section-title">文件类型分布</h3>
          </div>
          <div class="type-list">
            <div v-for="(count, type) in stats.file_types || {}" :key="type" class="type-row">
              <div class="type-info">
                <span class="type-dot" :class="`dot-${type.replace('.','')}`"></span>
                <span class="type-name">{{ type }}</span>
              </div>
              <div class="type-bar-wrap">
                <div class="type-bar" :style="{width: barWidth(count) + '%'}"></div>
              </div>
              <span class="type-count">{{ count }}</span>
            </div>
          </div>
        </section>

        <!-- 快捷操作 -->
        <section class="shell-panel quick-actions">
          <div class="section-head">
            <h3 class="section-title">快捷操作</h3>
          </div>
          <div class="action-list">
            <RouterLink to="/documents" class="action-item">
              <div class="action-icon action-icon--blue"><el-icon><Upload /></el-icon></div>
              <div>
                <p class="action-title">上传文档</p>
                <p class="action-desc">支持 PDF / Word / Excel 等格式</p>
              </div>
            </RouterLink>
            <RouterLink to="/search" class="action-item">
              <div class="action-icon action-icon--green"><el-icon><Search /></el-icon></div>
              <div>
                <p class="action-title">智能检索</p>
                <p class="action-desc">混合检索 + LLM 增强问答</p>
              </div>
            </RouterLink>
          </div>
        </section>
      </div>
    </div>

    <DocumentViewerModal
      v-if="viewerDoc"
      v-model:visible="viewerVisible"
      :document-id="viewerDoc.id || viewerDoc.document_id"
      :filename="viewerDoc.filename"
      :file-type="viewerDoc.file_type"
      :file-available="viewerDoc.file_available"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Document, Folder, DataBoard, Grid, Upload, Search } from '@element-plus/icons-vue'
import DocumentViewerModal from '@/components/DocumentViewerModal.vue'
import { api } from '@/api'

const recentDocs = ref([])
const stats = ref({})
const viewerVisible = ref(false)
const viewerDoc = ref(null)

const openViewer = (doc) => {
  viewerDoc.value = doc
  viewerVisible.value = true
}

const totalDocuments = ref(0)
const classifiedCount = computed(() => recentDocs.value.filter(d => d.classification_result).length)

const maxCount = computed(() => Math.max(...Object.values(stats.value.file_types || {1:1}), 1))
const barWidth = (count) => Math.round((count / maxCount.value) * 100)

const formatDate = (iso) => {
  if (!iso) return ''
  return iso.replace('T', ' ').slice(0, 16)
}

onMounted(async () => {
  const [docsRes, statsRes] = await Promise.all([api.getDocumentList(1, 20), api.getStats()])
  recentDocs.value = docsRes.data?.items || []
  totalDocuments.value = docsRes.data?.total || recentDocs.value.length
  stats.value = statsRes.data || {}
})
</script>

<style scoped lang="scss">
.dashboard { display: flex; flex-direction: column; gap: 20px; }

/* 指标行 */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
}

.metric-icon {
  width: 40px; height: 40px;
  border-radius: 10px;
  display: grid; place-items: center;
  font-size: 18px;
  flex-shrink: 0;

  &--blue   { background: var(--blue-50);  color: var(--blue-600); }
  &--green  { background: var(--green-50); color: var(--green-600); }
  &--amber  { background: var(--amber-50); color: var(--amber-600); }
  &--purple { background: #F5F3FF;         color: #7C3AED; }
}

.metric-label {
  font-size: 12px;
  color: var(--ink-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metric-value {
  display: block;
  font-size: 26px;
  font-weight: 700;
  color: var(--ink-strong);
  letter-spacing: -0.02em;
  line-height: 1.2;
  margin-top: 2px;
}

/* 主网格 */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 20px;
  align-items: start;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-strong);
}

.link-more {
  font-size: 12px;
  color: var(--blue-600);
  &:hover { text-decoration: underline; }
}

/* 表格单元 */
.file-cell {
  display: flex; align-items: center; gap: 8px;

  &.clickable {
    cursor: pointer;
    .filename-text { color: var(--blue-600); }
    &:hover .filename-text { text-decoration: underline; }
  }
}

.filename-text {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 180px;
  font-size: 13px;
  color: var(--ink-strong);
}

.text-muted { color: var(--ink-muted); font-size: 12px; }

/* 文件类型彩点 */
.file-type-dot, .type-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}

.dot-pdf   { background: #EF4444; }
.dot-docx, .dot-doc  { background: var(--blue-600); }
.dot-xlsx, .dot-xls  { background: var(--green-600); }
.dot-pptx, .dot-ppt  { background: #F97316; }
.dot-txt   { background: #8B5CF6; }
.dot-eml, .dot-msg   { background: var(--amber-600); }

/* 侧栏 */
.side-col { display: flex; flex-direction: column; gap: 14px; }

/* 类型分布 */
.type-list { display: flex; flex-direction: column; gap: 10px; }

.type-row {
  display: flex; align-items: center; gap: 8px;
}

.type-info {
  display: flex; align-items: center; gap: 6px;
  width: 60px; flex-shrink: 0;
}

.type-name { font-size: 12px; color: var(--ink-body); }

.type-bar-wrap {
  flex: 1;
  height: 6px;
  background: var(--bg-subtle);
  border-radius: 999px;
  overflow: hidden;
}

.type-bar {
  height: 100%;
  background: var(--blue-600);
  border-radius: 999px;
  transition: width 0.4s ease;
  min-width: 4px;
}

.type-count {
  font-size: 12px;
  color: var(--ink-muted);
  width: 24px;
  text-align: right;
}

/* 快捷操作 */
.action-list { display: flex; flex-direction: column; gap: 10px; }

.action-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  transition: border-color 0.15s, background 0.15s;
  cursor: pointer;

  &:hover {
    border-color: var(--blue-600);
    background: var(--blue-50);
  }
}

.action-icon {
  width: 36px; height: 36px;
  border-radius: 8px;
  display: grid; place-items: center;
  font-size: 16px;
  flex-shrink: 0;

  &--blue  { background: var(--blue-50);  color: var(--blue-600); }
  &--green { background: var(--green-50); color: var(--green-600); }
}

.action-title { font-size: 13px; font-weight: 600; color: var(--ink-strong); }
.action-desc  { font-size: 12px; color: var(--ink-muted); margin-top: 2px; }

@media (max-width: 1100px) {
  .metrics-row { grid-template-columns: repeat(2, 1fr); }
  .main-grid   { grid-template-columns: 1fr; }
}
</style>
