# LightRAG Large-Doc Chunking And LLM Throttling Design

## Context

当前大文档失败的主因已经从连接问题转移到 LightRAG 内部的长耗时抽取阶段。

现状有两个关键事实：

1. `APIConnectionError` 链路已经修复，`6008`、`8011`、`9621` 当前健康。
2. 大文档仍可能在 LightRAG 的实体/关系抽取阶段失败，典型报错为 `LLM func: Worker execution timeout after 360s`。

这说明当前瓶颈不再是 embedding 服务可达性，而是大文档切片过多后触发的 LLM 并发与长任务堆积问题。

LightRAG 当前已经支持：

- 全局 `chunk_token_size`
- 全局 `llm_model_max_async`
- 包装后的 LLM / embedding 调用限流

但它缺少两项对这次问题直接有效的能力：

- 按文档动态放大 chunk size，减少大文档切片总数
- 在 LLM 调用链路增加更强的全局/局部异步并发控制，避免单个大文档冲垮整个处理队列

## Goals

1. 自动识别大文档，并仅对大文档启用更大的 chunk size。
2. 在不拖慢普通文档的前提下，显著降低大文档的切片总数。
3. 为 LightRAG 的 LLM 调用层补上全局与局部双层异步并发控制。
4. 降低大文档在实体/关系抽取阶段发生 worker timeout 的概率。
5. 保持 DocAgentRAG 现有上传、重处理、状态同步链路不变，只在必要处透传或补测试。

## Non-Goals

1. 不重写 DocAgentRAG 自己的文档解析或分块主链。
2. 不引入新的文档上传协议或前端交互。
3. 不对所有文档统一放大 chunk size。
4. 不把整个系统改成完全串行处理。
5. 不在本次改造中追求最大吞吐，优先目标是稳定性和可恢复性。

## Requirements

### Functional Requirements

1. 系统必须能够在 LightRAG 处理文档时识别“普通文档”和“大文档”。
2. 大文档判定必须基于预计 chunk 数，而不是文件字节大小。
3. 大文档在真正切片时必须使用单独的 chunk profile。
4. 普通文档必须继续使用当前默认 chunk profile。
5. LightRAG 的 LLM 调用层必须同时受到全局并发控制和局部并发控制。
6. 单个大文档不能独占全部 LLM 并发额度。

### Operational Requirements

1. 已有文档上传接口与重处理接口保持兼容。
2. 现有 `6008 -> 9621` 代理方式不变。
3. 改动应尽量局限在 LightRAG 运行层与少量 DocAgentRAG 适配层。
4. 必须有自动化回归测试覆盖大文档 profile 选择与 LLM 节流行为。

## Decision

采用“文档级 large-doc profile + LLM 双层 Semaphore”方案。

### Why This Approach

相比“仅调低全局并发和全局增大 chunk”的方案，这个方案更适合当前问题：

- 它只对大文档收紧，不惩罚普通文档
- 它直接作用在 LightRAG 真正执行切片和抽取的层面
- 它不需要改变前端或 DocAgentRAG 的上传语义
- 它与现有 LightRAG 全局参数兼容，可以作为向后兼容的增强

## Architecture

### 1. Large-Doc Detection

大文档判定以“预计 chunk 数阈值”为准。

判定公式：

- `estimated_chunks = ceil(content_length / default_chunk_token_size)`

其中：

- `content_length` 使用 LightRAG 已经写入 `doc_status` 的内容长度
- `default_chunk_token_size` 使用当前实例默认 `chunk_token_size`

当 `estimated_chunks >= LARGE_DOC_THRESHOLD_CHUNKS` 时，文档被标记为大文档。

默认建议值：

- `LARGE_DOC_THRESHOLD_CHUNKS = 80`

### 2. Large-Doc Profile

被识别为大文档的文档，在 `doc_status.metadata` 中写入 profile：

```json
{
  "large_doc_profile": {
    "enabled": true,
    "estimated_chunks": 96,
    "chunk_token_size": 2400,
    "chunk_overlap_token_size": 150,
    "chunk_max_async": 1
  }
}
```

普通文档不写该字段，或者写入 `enabled=false` 的空 profile。

设计上选择将 profile 持久化到 `doc_status.metadata`，原因是：

- LightRAG 当前已有稳定的 `metadata` 存储与透出能力
- 上传后异步处理、失败重试、重处理都能复用同一份 profile
- 不需要为本次改造新建表或新建 sidecar 存储

### 3. Dynamic Chunking

在 LightRAG 真正调用 `chunking_func` 之前，根据文档级 profile 选择实际使用的参数：

- 普通文档：使用实例默认 `chunk_token_size` 和 `chunk_overlap_token_size`
- 大文档：使用 `metadata.large_doc_profile` 中的专用值

这意味着“动态放大 chunk size”发生在文档处理时，而不是在实例启动时全局改配置。

默认建议值：

- 普通文档：`chunk_token_size = 1200`
- 大文档：`chunk_token_size = 2400`
- 普通 overlap：`100`
- 大文档 overlap：`150`

### 4. LLM Dual-Layer Concurrency Control

#### Global Gate

保留并继续使用 LightRAG 当前基于 `llm_model_max_async` 的全局限流。

默认建议值：

- `MAX_ASYNC = 2`

#### Local Gate

在 chunk 抽取阶段增加局部 `Semaphore`。

局部 gate 的职责是限制“单个文档在 chunk 级别可同时发起的 LLM 抽取任务数量”。

行为规则：

- 普通文档默认沿用当前全局并发上限
- 大文档使用更小的 `chunk_max_async`
- 默认大文档 `chunk_max_async = 1`

这样可以保证：

- 全局 gate 控制系统总水位
- 局部 gate 控制单文档洪峰

两层同时存在时，单个大文档必须同时通过：

1. 文档自身的局部 semaphore
2. 系统实例的全局 semaphore

## Component Design

### LightRAG Runtime Layer

主要改动位于 LightRAG 运行层。

目标文件：

- `backend/.venv/lib/python3.12/site-packages/lightrag/lightrag.py`
- `backend/.venv/lib/python3.12/site-packages/lightrag/operate.py`

职责拆分如下：

#### `lightrag.py`

- 增加大文档 profile 计算逻辑
- 将 profile 持久化到 `doc_status.metadata`
- 在处理单文档时读取 profile 并选择实际 chunk 参数
- 将文档级局部并发参数传给实体抽取流程

#### `operate.py`

- 在 chunk 级抽取入口读取文档级局部并发参数
- 为单文档抽取任务创建局部 semaphore
- 保持当前全局 LLM 包装逻辑不变，只在其外层增加局部 gate

### DocAgentRAG Adaptation Layer

DocAgentRAG 侧不重写主逻辑，只做三类工作：

1. 补测试，锁定接口兼容性
2. 在 dev env 中保留保守全局默认值
3. 如有必要，提供 profile 相关配置项生成

目标文件预计包括：

- `backend/app/services/lightrag_dev_config.py`
- `backend/test/test_lightrag_dev_config.py`
- `backend/test/test_lightrag_client.py`
- 以及新增的 LightRAG patch 回归测试

## Data Flow

### Upload / Initial Processing

1. 文档上传进入 LightRAG。
2. LightRAG 完成文本抽取并写入 `doc_status.content_length`。
3. 在文档进入切片阶段前，系统根据 `content_length` 估算 chunk 数。
4. 若超过阈值，则将 large-doc profile 写入 `doc_status.metadata`。
5. 后续切片与抽取阶段按照该 profile 执行。

### Reprocess Failed

1. 失败文档进入重处理队列。
2. 如果文档已有 `metadata.large_doc_profile`，直接复用。
3. 如果历史失败文档没有该 metadata，则在重处理前重新计算。
4. 重处理后的文档继续沿用统一的动态 chunk / 双层限流策略。

## Error Handling

### Metadata Missing

如果文档 `metadata` 缺失或结构非法：

- 回退到默认普通文档策略
- 重新根据 `content_length` 计算 profile

### Content Length Missing

如果 `content_length` 缺失或为非法值：

- 不判定为大文档
- 使用默认 chunk profile
- 在日志中记 warning，但不阻断处理

### Invalid Profile Values

如果 metadata 中 profile 数值异常：

- 归一化到安全边界
- 最小值不得低于默认 chunk 行为的基本有效范围
- 最大值不得超过 LLM 上下文与系统允许范围

### Timeout Still Happens

如果大文档在新策略下仍然超时：

- 错误继续通过现有 `FAILED` 状态与 `error_msg` 暴露
- 日志中必须包含文档的 large-doc profile 信息，便于后续调参

## Configuration

本次设计保留现有保守全局配置，并新增大文档 profile 参数。

建议增加的环境变量：

- `LARGE_DOC_THRESHOLD_CHUNKS`
- `LARGE_DOC_CHUNK_SIZE`
- `LARGE_DOC_CHUNK_OVERLAP_SIZE`
- `LARGE_DOC_CHUNK_MAX_ASYNC`

默认建议值：

- `LARGE_DOC_THRESHOLD_CHUNKS=80`
- `LARGE_DOC_CHUNK_SIZE=2400`
- `LARGE_DOC_CHUNK_OVERLAP_SIZE=150`
- `LARGE_DOC_CHUNK_MAX_ASYNC=1`

现有保守默认值继续保留：

- `EMBEDDING_TIMEOUT=120`
- `EMBEDDING_BATCH_NUM=2`
- `EMBEDDING_FUNC_MAX_ASYNC=2`
- `MAX_ASYNC=2`
- `MAX_PARALLEL_INSERT=1`

## Testing Strategy

### Unit Tests

必须覆盖以下行为：

1. 给定 `content_length`，能够正确判断是否为大文档。
2. 大文档能够生成正确的 profile 并写入 metadata。
3. 普通文档不会错误使用大文档 chunk 参数。
4. 大文档在抽取阶段使用局部 semaphore。
5. 普通文档在没有 profile 时仍走默认路径。

### Regression Tests

必须增加两类回归：

1. 大文档 profile 在失败重处理场景中可复用或重建。
2. LLM 局部并发限制不会破坏现有上传/重处理主链。

### Runtime Verification

上线前至少验证：

1. 普通文档上传与处理不回退。
2. 大文档在日志中能看到 large-doc profile 生效。
3. 重处理失败文档时，状态不再迅速回落到旧的 360s timeout。

## Rollout Plan

1. 先补测试，锁定大文档 profile 选择与局部并发行为。
2. 再 patch LightRAG 运行层。
3. 保持现有 `6008` 和 `9621` 运行链路不变，只重载必要服务。
4. 用当前失败样本 `重构：改善既有代码的设计（第2版）...pdf` 做真实验证。
5. 若验证通过，再考虑是否把 profile 参数暴露到更显式的配置生成逻辑。

## Risks

1. LightRAG 安装在 `site-packages`，补丁需要谨慎控制范围，避免未来升级覆盖。
2. 动态增大 chunk size 可能降低抽取细粒度，少数边缘实体召回率可能下降。
3. 局部并发收紧后，大文档完成时间可能变长，但这是稳定性换吞吐的有意取舍。

## Acceptance Criteria

满足以下条件视为本次设计落地成功：

1. 大文档会自动被识别并应用更大的 chunk size。
2. 普通文档仍使用默认 chunk 策略。
3. 大文档抽取阶段存在文档级局部并发控制。
4. 系统仍保留全局 LLM 并发控制。
5. 指定失败样本在新策略下不再因为同样的并发/切片问题快速重现旧超时。
