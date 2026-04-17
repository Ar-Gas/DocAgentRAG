# LightRAG-Centric Migration Design

## Context

DocAgentRAG 当前已经有 `backend/app/*` 这一层壳，但核心链路仍然是本地实现：

- 上传后在本地做抽取、分块、Chroma 建索引
- 检索链路混合了向量检索、BM25、smart retrieval、LLM rerank
- QA 依赖本地 `gateway` 和 `qa_chain`
- 图谱页依赖本地 `graph_index`
- 前端搜索页围绕“文档列表 + 本地文本阅读器 + 主题树”组织

这套结构的主要问题不是功能缺失，而是核心职责重复。LightRAG 自己已经提供文档导入、结构化检索、RAG 问答、图谱查询和健康检查。继续在 DocAgentRAG 内部保留第二套本地 RAG 主链，只会让维护成本和故障面一起增加。

本设计的目标是把 DocAgentRAG 改成一个 LightRAG-first 的产品壳：

- LightRAG 负责检索、问答、图谱和知识抽取
- DocAgentRAG 负责本地文件保存、SQLite 元数据、业务 API 整形、前端交互

## Goals

1. 严格对齐官方 LightRAG Server 当前 API，而不是定义一套自创协议。
2. 删除 DocAgentRAG 内部的本地检索、分块索引、问答主链。
3. 保留本地文件与 SQLite 元数据，继续支持文档列表、上传、删除和基础状态展示。
4. 把前端搜索页和问答页一起改成 LightRAG 语义，而不是继续围绕旧 block reader 交互。
5. 让系统运行时默认以 LightRAG 为主，豆包配置只保留给可选的本地分类逻辑。

## Non-Goals

1. 不再兼容旧的 Chroma/BM25/smart retrieval 行为细节。
2. 不保留 `DocumentReader` 高亮定位、`TopicTreePanel`、`SummaryDrawer`、`ClassificationReportDrawer` 作为主检索交互。
3. 不在第一阶段重建一套新的本地图数据库或本地 block 索引体系。
4. 不要求前端继续保持旧工作台结果结构。

## Official LightRAG Baseline

本设计以 2026-04-17 查询的官方 `HKUDS/LightRAG` `main` 分支服务端源码为基线。

确认到的关键契约如下：

- 认证：
  - 当服务端启用 API Key 时，请求头使用 `X-API-Key`
- 健康检查：
  - `GET /health`
- 文档导入：
  - `POST /documents/upload`
  - `POST /documents/text`
  - `POST /documents/texts`
  - `GET /documents/track_status/{track_id}`
- 文档删除：
  - `DELETE /documents/delete_document`
- 查询：
  - `POST /query`
  - `POST /query/stream`
  - `POST /query/data`
- 图谱：
  - `GET /graphs`
  - `GET /graph/label/list`
- 查询模式：
  - `local`
  - `global`
  - `hybrid`
  - `naive`
  - `mix`
  - `bypass`

这意味着原始改造草案里“上传后直接拿到 doc_id 并立即写库”的假设不成立。官方上传接口首先返回 `track_id`，导入状态需要异步轮询。因此本地元数据模型必须显式记录 LightRAG 导入状态。

## Primary Design Decision

采用“官方契约优先 + DocAgentRAG 适配层”方案。

具体含义是：

- DocAgentRAG 后端继续暴露自己的 `/api/v1/*` 路由，减少前端跨域与权限散落
- 这些路由不再实现第二套 RAG，而是把请求转换成官方 LightRAG API
- 业务层唯一允许保留的本地职责，是文件持久化、SQLite 元数据、状态同步、结果整形和可选分类标签

不采用“尽量兼容旧结果结构”的原因有两个：

- 旧结构深度绑定本地 block reader 和 Chroma 元数据，不值得继续背
- SearchPage 和 QAPage 本来就要改，继续套壳只会把旧抽象带进新系统

## Backend Design

### Configuration

`backend/config.py` 增加以下配置：

- `LIGHTRAG_BASE_URL`
- `LIGHTRAG_API_KEY`
- `LIGHTRAG_TIMEOUT_SECONDS`
- `LIGHTRAG_QUERY_MODE_DEFAULT`

配置读取顺序：

1. `backend/secrets_api.py`
2. 环境变量
3. 安全默认值

豆包配置保留，但职责缩减为：

- 可选本地分类服务
- 未来可能保留的非核心辅助能力

检索、问答、图谱、导入健康检查不再直接依赖豆包配置。

### New Infra Client

新增 `backend/app/infra/lightrag_client.py`。

职责：

- 统一封装对 LightRAG 的 HTTP 调用
- 统一处理 `X-API-Key`
- 统一超时、异常映射、日志
- 统一把官方返回转成服务层可消费的 Python 结构

客户端提供的方法：

- `health()`
- `upload_file(file_path, filename) -> {status, track_id, message}`
- `insert_text(text, file_source=None) -> {status, track_id, message}`
- `insert_texts(texts, file_sources=None) -> {status, track_id, message}`
- `get_track_status(track_id) -> {documents, total_count, status_summary}`
- `query_data(text, mode, top_k, conversation_history=None) -> structured_result`
- `query(text, mode, include_references=True, include_chunk_content=True, conversation_history=None) -> answer_result`
- `query_stream(...) -> async byte/chunk iterator`
- `get_graph(label, max_depth=3, max_nodes=1000)`
- `list_graph_labels()`
- `delete_documents(doc_ids, delete_file=False, delete_llm_cache=False)`

### Metadata Model

SQLite 继续作为 DocAgentRAG 的本地元数据存储，但字段调整为 LightRAG-first。

文档元数据至少保留：

- `id`
- `filename`
- `filepath`
- `file_type`
- `created_at_iso`
- `classification_result`
- `lightrag_track_id`
- `lightrag_doc_id`
- `index_status`
- `index_error`
- `last_status_sync_at`

关键决策：

- `lightrag_track_id` 是上传后立即可得的外部标识
- `lightrag_doc_id` 在 LightRAG 导入完成后补写
- `index_status` 使用 DocAgentRAG 自己的归一化状态，例如 `queued / processing / ready / failed / deleted`

这是对原始方案的必要修正。只存 `lightrag 文档 ID` 不够，因为官方上传并不是同步 doc_id 模式。

### Document Service

`backend/app/services/document_service.py` 改成异步服务。

新上传流程：

1. 校验扩展名与大小
2. 保存原文件到本地 `backend/doc/*`
3. 在 SQLite 中写入一条本地记录，状态为 `queued`
4. 调用 `lightrag_client.upload_file()`
5. 如果 LightRAG 返回 `success`，把 `track_id` 写入本地记录
6. 如果 LightRAG 返回 `duplicated`，删除刚写入的本地文件和临时元数据，并把重复状态直接返回前端
7. 返回本地文档记录给前端

状态同步策略：

- 对 `queued / processing` 文档，`list_documents()` 与 `get_document()` 在读取前按节流策略调用 `get_track_status()`
- 如果 LightRAG 返回成功文档列表，则回填 `lightrag_doc_id` 和 `ready`
- 如果 LightRAG 返回失败，则记录 `index_error`

删除流程：

1. 如果已有 `lightrag_doc_id`，调用 `delete_documents([doc_id])`
2. 只有当远端返回“删除已接受”或“文档不存在”时，才继续本地删除
3. 删除本地文件
4. 删除 SQLite 元数据

如果本地记录还只有 `track_id` 没有 `doc_id`：

- 先尝试同步一次 track status
- 仍拿不到 doc_id 时，允许本地删除并记录远端删除跳过

### Retrieval Service

`backend/app/services/retrieval_service.py` 完全改写，不再依赖：

- `utils.retriever`
- `utils.smart_retrieval`
- `QueryAnalyzer`
- `GraphRetrieval`
- BM25
- Chroma

新检索主链直接调用 `lightrag_client.query_data()`。

服务层统一返回：

```json
{
  "query": "xxx",
  "mode_used": "hybrid",
  "results": [],
  "references": [],
  "metadata": {}
}
```

`results` 是对 LightRAG `entities / relationships / chunks` 的归一化结果，而不是旧的“按文档聚合 block”。

归一化规则：

- chunk 转成：
  - `kind: "chunk"`
  - `title: file_path`
  - `content`
  - `file_path`
  - `reference_id`
  - `chunk_id`
- relationship 转成：
  - `kind: "relationship"`
  - `title: "src -> tgt"`
  - `content: description`
  - `file_path`
  - `reference_id`
  - `keywords`
  - `weight`
- entity 转成：
  - `kind: "entity"`
  - `title: entity_name`
  - `content: description`
  - `entity_type`
  - `file_path`
  - `reference_id`

前端检索页按 `kind` 渲染，不再依赖本地阅读器。

### QA Service

`backend/app/services/qa_service.py` 改为 LightRAG 代理层。

同步问答：

- 调用 `lightrag_client.query()`
- 默认 mode 使用 `hybrid`

流式问答：

- 调用 `lightrag_client.query_stream()`
- 后端把官方 NDJSON 转成当前前端已在使用的 SSE 输出

SSE 输出保持简化：

- 内容帧：`{ "chunk": "..." }`
- 引用帧：`{ "references": [...] }`
- 完成帧：`{ "status": "complete", "session_id": "..." }`
- 错误帧：`{ "error": "..." }`

这样前端问答页可以只改接口地址和少量字段，不需要直接实现 NDJSON 解析器。

`doc_ids` 范围选择在第一阶段从前端移除。官方 LightRAG 当前查询主链是全库语义检索，先保证主流程简单可用。

### Topics and Graph

`backend/api/topics.py` 改成 LightRAG 图谱代理。

主入口：

- `GET /topics/graph`
  - 内部调用 `lightrag_client.get_graph(label, max_depth, max_nodes)`

辅助接口：

- 可新增 `GET /topics/labels`
  - 内部调用 `list_graph_labels()`

旧的 `GraphIndex`、`GraphStore`、`EntityRepository` 不再是图谱主链依赖。

### Classification

第一阶段保留现有 `classification_result` 字段，但从主链路脱钩。

约束如下：

- 上传成功与否只由本地保存和 LightRAG 导入决定
- 分类失败不能影响上传成功
- 搜索页、图谱页、问答页不再依赖分类结果

这样可以避免在同一个迁移中同时重写分类逻辑。

### Main Startup

`backend/main.py` 的启动流程改为：

1. 创建本地目录
2. 校验 `LIGHTRAG_BASE_URL`
3. 调用 `lightrag_client.health()`
4. 记录 LightRAG 可用性并启动 API

删除以下启动职责：

- Chroma collection 初始化
- block 索引审计与重建
- embedding 维度锁定

### Code Removal

确认新主链稳定后，删除下列模块或停止引用：

- `backend/utils/block_extractor.py`
- `backend/utils/retriever.py`
- `backend/utils/smart_retrieval.py`
- `backend/app/infra/vector_store.py`
- `backend/app/infra/embedding_provider.py`
- `backend/app/domain/llm/qa_chain.py`
- `backend/app/domain/llm/gateway.py`
- `backend/app/services/topic_tree_service.py`
- `backend/app/services/indexing_service.py`
- `backend/app/services/document_vector_index_service.py`
- `backend/app/services/ingest_pipeline.py`

如果某些文件仍被分类服务引用，则在分类与主链完全脱钩后再删，不做“先删再修”。

## Frontend Design

### API Layer

`frontend/docagent-frontend/src/api/index.js` 简化为四类接口：

- 文档：
  - `uploadDocument`
  - `getDocumentList`
  - `deleteDocument`
- 检索：
  - `lightragQueryData`
- 问答：
  - `streamLightRagQA`
  - `lightRagQA`
- 图谱：
  - `getGraph`
  - `getGraphLabels`

删除旧接口：

- `workspaceSearchStream`
- `summarizeResults`
- `generateClassificationTable`
- `streamQA` 的旧实现
- 其他旧工作台拼装接口

### Documents Page

文档列表页继续保留，但展示字段调整为：

- 文件名
- 文件类型
- 上传时间
- `index_status`
- `classification_result`

上传成功后的前端语义也调整：

- 不再代表“本地抽取和索引已完成”
- 只代表“文件已保存且已成功提交给 LightRAG”

前端需要能看到 `queued / processing / ready / failed`。

### Search Page

`SearchPage.vue` 改成结果流视图，不再是“文档列表 + 阅读器”联动。

模式下拉改成：

- `naive`
- `local`
- `global`
- `hybrid`
- `mix`

`bypass` 不放在主界面，因为它是“跳过检索直接问 LLM”，不适合作为搜索页默认能力。

页面行为：

- 输入 query 后调用后端 `/retrieval/query`
- 结果列表按 `kind` 渲染
- chunk 结果显示文件路径和正文片段
- relationship 结果显示关系描述与权重
- entity 结果显示实体类型和描述

页面删除以下依赖：

- `DocumentReader`
- `TopicTreePanel`
- `SummaryDrawer`
- `ClassificationReportDrawer`

### QA Page

`QAPage.vue` 改为全库问答页。

第一阶段移除：

- 文档范围多选

保留：

- SSE 流式答案展示
- 引用列表展示
- 会话 ID

后端会继续用 SSE 包装 LightRAG NDJSON，因此前端不需要直接实现 NDJSON 解析。

### Graph Page

`GraphPage.vue` 与 `GraphCanvas.vue` 适配官方图谱结构。

页面流程：

1. 先调用 `/topics/labels`
2. 选中标签后调用 `/topics/graph?label=...`
3. 把 LightRAG 返回节点和边映射到现有图组件需要的结构

如果现有 `GraphCanvas` 假设了旧字段名，就在前端做一层纯映射，不再从后端伪造旧图谱格式。

### Frontend Removal

替换完成后可删除：

- `TaxonomyPage.vue`
- `useSearch.js`
- `useDocumentReader.js`
- `useSummary.js`
- `ClassificationPanel.vue`
- `DocumentReader.vue`
- `TopicTreePanel.vue`
- `SummaryDrawer.vue`
- `ClassificationReportDrawer.vue`

## End-to-End Data Flow

### Upload

```text
Browser upload
  -> DocAgentRAG /documents/upload
  -> save local file
  -> save SQLite row(status=queued)
  -> POST LightRAG /documents/upload
  -> persist track_id
  -> browser polls document list
  -> backend syncs /documents/track_status/{track_id}
  -> row becomes ready/failed
```

### Search

```text
Browser SearchPage
  -> DocAgentRAG /retrieval/query
  -> POST LightRAG /query/data
  -> normalize entities/relationships/chunks
  -> render result cards by kind
```

### QA

```text
Browser QAPage
  -> DocAgentRAG /qa/stream
  -> POST LightRAG /query/stream
  -> NDJSON to SSE transform
  -> incremental answer rendering
```

### Graph

```text
Browser GraphPage
  -> DocAgentRAG /topics/labels
  -> GET LightRAG /graph/label/list
  -> DocAgentRAG /topics/graph
  -> GET LightRAG /graphs
  -> graph field mapping
```

## Error Handling

错误处理原则统一如下：

- LightRAG 不可达：
  - 返回 502 类业务错误
  - 前端提示“LightRAG 服务不可用”
- 上传已被 LightRAG 判重：
  - 本地元数据写入已有状态或重复提示
- 查询模式非法：
  - 在后端参数校验阶段直接拒绝
- 图谱 label 缺失：
  - 后端返回 400，不做默认猜测

不做的事情：

- 不在 LightRAG 失败时回退到旧 Chroma/BM25
- 不同时维护“双检索主链”

## Testing Strategy

### Backend

新增和改写测试至少覆盖：

- `lightrag_client`：
  - API key 注入
  - 超时映射
  - 非 2xx 响应映射
- `document_service`：
  - 上传成功后写入 `track_id`
  - `track_status` 同步成功后回填 `lightrag_doc_id`
  - LightRAG 上传失败时本地状态写成 failed
- `retrieval_service`：
  - `/query/data` 结果归一化为 `chunk / relationship / entity`
- `qa_service`：
  - NDJSON 转 SSE
- `topics`：
  - 图谱字段映射

### Frontend

至少验证：

- SearchPage 新模式切换和结果渲染
- QAPage 流式输出
- GraphPage 标签加载和图谱展示
- 文档列表页状态展示

## Rollout Plan

推荐按以下顺序实现：

1. 引入 `lightrag_client`，打通 `/health`
2. 改造 `document_service` 和文档列表状态同步
3. 改造 `retrieval_service`，让 SearchPage 能吃到 `/query/data`
4. 改造 `qa_service` 和 QAPage 流式链路
5. 改造 graph 接口和 GraphPage
6. 停止主链路对旧检索/问答模块的引用
7. 删除死代码和旧依赖

## Acceptance Criteria

迁移完成后，满足以下条件才算完成：

1. 上传一个文档后，文档列表能看到 `queued -> ready` 或 `failed` 的状态变化。
2. SearchPage 使用 LightRAG 模式查询，结果不再依赖本地阅读器。
3. QAPage 能基于 LightRAG 流式返回答案。
4. GraphPage 能加载 LightRAG 图谱。
5. `backend/main.py` 启动不再初始化 Chroma 或 block index。
6. 后端主链已不再调用本地 BM25、Chroma、`qa_chain`、`gateway`。
