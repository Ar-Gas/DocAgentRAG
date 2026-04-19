<template>
  <section class="rag-studio-page">
    <div class="studio-header shell-panel">
      <div>
        <h3>RAG 工作台</h3>
        <p>将知识库能力嵌入毕业设计演示界面，保持你的系统作为主入口。</p>
      </div>
      <a class="studio-link" href="/api/v1/admin/lightrag/webui/" target="_blank" rel="noreferrer">
        新窗口打开
      </a>
    </div>

    <div class="studio-frame-wrap shell-panel">
      <iframe
        class="studio-frame"
        src="/api/v1/admin/lightrag/webui/"
        title="RAG 工作台"
      />
    </div>
  </section>
</template>

<style scoped lang="scss">
.rag-studio-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: calc(100vh - 112px);
}

.studio-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--ink-strong);
    margin-bottom: 4px;
  }

  p {
    font-size: 13px;
    color: var(--ink-muted);
  }
}

.studio-link {
  color: var(--blue-600);
  font-size: 13px;
  font-weight: 600;
}

.studio-frame-wrap {
  flex: 1;
  padding: 0;
  overflow: hidden;
}

.studio-frame {
  width: 100%;
  min-height: calc(100vh - 220px);
  border: 0;
  background: #fff;
}
</style>
