# Extracted Content Shard Ingest Design

## Context

当前 LightRAG 主链路已经恢复可用，`bge-m3` 工作目录兼容问题和启动期缺失文档重排队问题也已经修复。

剩余稳定性问题集中在大文档：

1. 文档上传时只能看到原始文件大小，不能准确反映实际要送入 LightRAG 的正文规模。
2. 同一份大文档在提取出正文后，往往因为正文过长导致 LightRAG 处理耗时高、失败率高，最终效果反而不如 `bge-m3` 的历史稳定状态。
3. 现有链路里，一个文档 ID 对应一次 LightRAG ingest，没有“提取后按正文大小拆分再顺序处理”的能力。

用户要求本次改造以“提取后的实际正文大小”为准进行拆分，分片文件名使用 `-1`、`-2` 等后缀。

## Goals

1. 基于提取后的实际正文长度判断是否需要分片，而不是基于上传文件字节数。
2. 将超限正文拆成多个逻辑子文档，按顺序送入 LightRAG。
3. 分片文件名保持原扩展名，显示为 `name-1.ext`、`name-2.ext`。
4. 保留原始上传文档作为父记录，聚合展示本地提取和 RAG ingest 状态。
5. 不破坏现有上传 API、文档列表 API、LightRAG 兼容工作目录和 `bge-m3` 默认模型。

## Non-Goals

1. 不改上传协议，不让前端上传多个物理文件。
2. 不改原始文件在磁盘上的真实存储路径。
3. 不在本次改造里引入新的页面交互。
4. 不重做现有 block index / reader payload 主逻辑。

## Decision

采用“父文档 + 提取后逻辑分片子文档 + 子文档顺序 ingest”方案。

### Why This Approach

相比“直接把一份提取结果强行压进 LightRAG”：

1. 它能直接作用在真正的风险点，也就是提取后的正文大小。
2. 它不需要变更上传流程或物理文件存储。
3. 它允许父文档继续作为 UI 主对象，同时把 LightRAG ingest 的实际执行粒度降到更稳的范围。

相比“只调大 LightRAG chunk size”：

1. 分片可以更确定地控制单次 ingest 的正文上限。
2. 失败重试可以只针对出问题的分片，而不是整份原文。
3. 可以显式保留分片级状态和错误。

## Data Model

在 `documents` 记录中增加以下逻辑字段：

- `parent_document_id`: 父文档 ID，父文档为空，分片子文档指向原始文档
- `is_shard`: 是否为逻辑分片
- `shard_index`: 分片序号，从 `1` 开始
- `shard_count`: 父文档感知到的总分片数
- `shard_content_length`: 当前分片正文长度
- `shard_group_id`: 同一父文档分片组标识，默认复用父文档 ID

父文档仍然保留原始上传元数据、原始文件路径、完整提取内容和预览内容。

分片子文档：

1. 共享原始 `filepath`
2. 持有各自独立的 `document_contents`
3. 持有各自独立的 `document_segments`
4. 持有各自独立的 `document_artifacts`
5. 持有各自独立的 `ingest_status`、`ingest_error`、`lightrag_track_id`、`lightrag_doc_id`

## Threshold And Split Rules

### Oversize Detection

是否需要分片使用提取后的 `full_content_length`。

默认规则：

- `LIGHTRAG_SHARD_CONTENT_THRESHOLD = 120000`
- `LIGHTRAG_SHARD_TARGET_SIZE = 90000`
- `LIGHTRAG_SHARD_HARD_LIMIT = 100000`

当 `full_content_length < LIGHTRAG_SHARD_CONTENT_THRESHOLD` 时，不创建分片，原文档继续按原逻辑 ingest。

当 `full_content_length >= LIGHTRAG_SHARD_CONTENT_THRESHOLD` 时，原文档进入“父文档 + 分片子文档”模式。

### Split Algorithm

正文拆分按以下优先级执行：

1. 优先按空行分段的段落边界切分
2. 若单段仍超过 `LIGHTRAG_SHARD_HARD_LIMIT`，再退化为按字符窗口硬切
3. 保持原文顺序，不重排内容
4. 每个分片尽量接近 `LIGHTRAG_SHARD_TARGET_SIZE`，但不得超过 `LIGHTRAG_SHARD_HARD_LIMIT`

### Split Naming

设原文件显示名为 `report.pdf`：

- 第 1 片：`report-1.pdf`
- 第 2 片：`report-2.pdf`
- 第 N 片：`report-N.pdf`

## Runtime Flow

### 1. Upload

上传行为不变，仍先创建原始文档记录。

### 2. Local Extraction

`process_local_index()` 成功后：

1. 保存父文档完整正文
2. 根据提取后的 `full_content_length` 判断是否需要分片
3. 若不需要分片，沿用现有逻辑
4. 若需要分片：
   - 创建或刷新子文档记录
   - 为每个子文档写入对应的正文、预览、长度等内容记录
   - 将父文档标记为分片聚合对象，不直接进入 LightRAG ingest

### 3. LightRAG Ingest

父文档若存在分片，则 `process_pending_ingest(parent_id)` 的行为变为：

1. 不上传父文档自身
2. 找出所有子分片，按 `shard_index` 排序
3. 逐个调用子分片的 ingest
4. 任何一个子分片失败时，父文档聚合状态标记为失败
5. 全部分片 ready 时，父文档聚合状态标记为 ready

未分片文档继续使用当前单文档 ingest 行为。

## Parent And Child Status Aggregation

父文档状态按子分片聚合：

1. 任一子分片 `failed`，父文档 `ingest_status = failed`
2. 全部子分片 `ready`，父文档 `ingest_status = ready`
3. 任一子分片 `processing`，父文档 `ingest_status = processing`
4. 任一子分片 `queued` 且无 `failed` / `processing`，父文档 `ingest_status = queued`
5. 若所有子分片均 `local_only`，父文档 `ingest_status = local_only`

父文档 `local_index_status` 依然以父文档正文提取结果为准；若分片创建失败，则父文档本地索引阶段失败。

父文档 `ingest_error` 聚合为第一个失败分片的错误信息。

## Retry Semantics

1. 重试父文档 ingest 时，如果父文档有分片，则重置所有子分片为 `queued`，然后按顺序重新执行。
2. 重试单个子分片时，只影响该子分片；父文档聚合状态在下一次读取或同步时刷新。
3. 删除父文档时，同时删除其全部子分片的元数据与衍生内容；原始物理文件只删除一次。

## API / UI Impact

默认列表接口继续返回父文档。

文档详情接口增加：

- `is_shard`
- `parent_document_id`
- `shards`: 当前父文档的子分片摘要列表

这样前端可以先保持原样，后续需要时再展示分片进度。

## Error Handling

1. 提取成功但分片创建失败：父文档 `local_index_status = failed`，不进入分片 ingest。
2. 分片创建成功但某片 ingest 失败：失败信息落在子分片和父文档聚合状态上。
3. 父文档读取时若发现分片元数据缺失，则允许重新生成缺失分片，而不是默默吞掉。

## Testing

至少需要以下回归覆盖：

1. 超限正文在提取后创建多个子分片
2. 分片命名为 `name-1.ext`、`name-2.ext`
3. 分片内容按顺序拼接后与原正文一致
4. 父文档存在分片时不会直接上传自身
5. 子分片会按 `shard_index` 顺序 ingest
6. 父文档正确聚合子分片状态与错误
7. 未超限文档继续走原路径，不创建分片
