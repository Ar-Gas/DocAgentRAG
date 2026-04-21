# Taxonomy V3 Hierarchical Classification Design

## Goal

Replace the current narrow enterprise-office taxonomy classification path with a broad, fixed three-level `taxonomy_v3` classifier that always returns a concrete leaf category for classifiable documents.

The user-facing goal is to stop normal documents from landing in mysterious `未分类 / 待复核 / no_match` states. Classification should cover both office documents and general knowledge-base content such as programming books, operating-system textbooks, social-science books, finance/history books, research reports, technical guides, and common business documents.

## Current Problems

The current classifier is too narrow and too rejection-heavy for the actual corpus:

- The existing taxonomy is mostly enterprise-office oriented.
- Many files are books, tutorials, academic materials, technical manuals, and research content.
- The classifier can return `classification_issue_code=no_match`, which the frontend displays as `未分类 / 待复核`.
- Some out-of-domain books are forced into unrelated enterprise labels, such as `知识产权` or `运维手册`.
- LightRAG or embedding ingest failures are visually mixed with classification status on `/documents`, making ingestion failures look like classification failures.

This design changes the classification contract: for normal documents with usable filename or content signals, the classifier should return a real taxonomy leaf. Low-certainty cases must fall back to a domain-specific concrete leaf, not `no_match`.

## Decisions

- Classification taxonomy version: `taxonomy_v3`.
- Directory shape: fixed three levels, `一级域 / 二级类 / 三级叶子类`.
- Coverage model: general knowledge base, not enterprise-office only.
- Classification flow: two-stage LLM classification.
- Fallback model: every top-level domain has at least one concrete fallback leaf.
- Existing documents: reclassify through an explicit batch entry point, not automatic full-database migration on startup.
- Normal classification results must not write `classification_issue_code=no_match`.

## Taxonomy Shape

`taxonomy_v3` should start with 13 top-level domains:

- `办公文档`
- `财务税务`
- `人力组织`
- `法务合规`
- `产品项目`
- `研发技术`
- `运维安全`
- `数据分析`
- `销售商务`
- `市场品牌`
- `客户服务`
- `图书资料`
- `研究分析`

The initial catalog should contain about 50 second-level categories and about 220 to 320 third-level leaves. The catalog should be large enough for broad coverage but still small enough for stable domain-scoped LLM selection.

Each leaf record should include:

```python
{
    "id": "books.computer.programming_language",
    "path": ["图书资料", "计算机图书", "编程语言书籍"],
    "label": "编程语言书籍",
    "description": "编程语言教程、实战书籍、语法和工程实践类图书。",
    "aliases": ["编程书籍", "语言教程", "Programming Book"],
    "keywords": ["编程", "语言", "教程", "示例代码", "Rust", "C++", "Python"],
    "fallback": False,
}
```

Each top-level domain must have exactly one preferred fallback leaf. Fallback leaves are real categories, not pseudo states:

- `办公文档 / 综合办公 / 通用办公材料`
- `财务税务 / 综合财务 / 通用财务材料`
- `人力组织 / 综合人事 / 通用人事材料`
- `法务合规 / 综合法务 / 通用法务材料`
- `产品项目 / 综合项目 / 通用项目材料`
- `研发技术 / 综合技术 / 通用技术文档`
- `运维安全 / 综合运维 / 通用运维材料`
- `数据分析 / 综合分析 / 通用分析材料`
- `销售商务 / 综合销售 / 通用销售材料`
- `市场品牌 / 综合市场 / 通用市场材料`
- `客户服务 / 综合服务 / 通用服务材料`
- `图书资料 / 综合图书 / 综合书籍`
- `研究分析 / 综合研究 / 通用研究材料`

## Suggested Category Coverage

The catalog should include at least the following second-level groups and representative leaves.

### 办公文档

Second-level groups:

- `综合办公`
- `会议纪要`
- `制度流程`
- `行政后勤`

Representative leaves:

- `通用办公材料`
- `会议纪要`
- `管理制度`
- `通知公告`
- `申请审批`
- `工作汇报`

### 财务税务

Second-level groups:

- `出纳结算`
- `报销付款`
- `账务报表`
- `预算成本`
- `税务管理`

Representative leaves:

- `出纳管理`
- `费用报销`
- `付款审批`
- `财务月报`
- `预算申请`
- `税务申报`

### 人力组织

Second-level groups:

- `招聘录用`
- `员工关系`
- `绩效薪酬`
- `培训发展`

Representative leaves:

- `招聘需求`
- `Offer审批`
- `入职材料`
- `离职办理`
- `绩效考核`
- `培训计划`

### 法务合规

Second-level groups:

- `合同协议`
- `审查意见`
- `知识产权`
- `授权资质`
- `隐私合规`

Representative leaves:

- `标准合同`
- `法务审查`
- `知识产权`
- `授权文件`
- `隐私条款`

### 产品项目

Second-level groups:

- `需求规划`
- `项目管理`
- `交付验收`
- `用户研究`

Representative leaves:

- `需求文档`
- `版本规划`
- `项目计划`
- `验收清单`
- `用户调研`

### 研发技术

Second-level groups:

- `架构设计`
- `接口文档`
- `开发规范`
- `测试质量`
- `技术方案`

Representative leaves:

- `架构设计`
- `接口文档`
- `开发手册`
- `测试用例`
- `技术方案`

### 运维安全

Second-level groups:

- `运维体系`
- `监控告警`
- `故障应急`
- `安全治理`
- `变更资产`

Representative leaves:

- `运维手册`
- `巡检记录`
- `故障复盘`
- `安全规范`
- `变更记录`

### 数据分析

Second-level groups:

- `经营分析`
- `专题分析`
- `报表看板`
- `数据治理`

Representative leaves:

- `分析报告`
- `经营复盘`
- `数据周报`
- `指标口径`
- `报表说明`

### 销售商务

Second-level groups:

- `售前方案`
- `报价投标`
- `客户合同`
- `客户跟进`

Representative leaves:

- `销售方案`
- `商务报价`
- `投标应答`
- `销售合同`
- `拜访记录`

### 市场品牌

Second-level groups:

- `市场策划`
- `活动运营`
- `品牌管理`
- `内容营销`
- `竞品研究`

Representative leaves:

- `市场方案`
- `活动策划`
- `品牌规范`
- `推广素材`
- `竞品分析`

### 客户服务

Second-level groups:

- `服务体系`
- `工单运营`
- `客户反馈`
- `投诉处理`

Representative leaves:

- `服务手册`
- `工单周报`
- `客户反馈`
- `投诉记录`
- `SLA协议`

### 图书资料

Second-level groups:

- `计算机图书`
- `经济金融图书`
- `社科图书`
- `科技产业图书`
- `综合图书`

Representative leaves:

- `编程语言书籍`
- `计算机基础教材`
- `软件工程书籍`
- `金融历史书籍`
- `社会学书籍`
- `互联网产业书籍`
- `综合书籍`

### 研究分析

Second-level groups:

- `行业研究`
- `学术论文`
- `政策研究`
- `咨询报告`
- `综合研究`

Representative leaves:

- `行业报告`
- `学术论文`
- `政策解读`
- `咨询报告`
- `通用研究材料`

## Two-Stage LLM Flow

The classifier should use a serialized, constrained LLM protocol. It should not ask the model to invent labels.

### Input Sampling

The classifier input should include:

- Filename
- File extension
- Content sample

The default content sample should use the first 2400 characters. If the leading sample appears noisy, such as cover-only text, copyright page, table of contents, whitespace-only extraction, or scan artifacts, the classifier should add short middle and tail samples. This keeps the prompt simple while reducing book-cover and table-of-contents bias.

### Stage 1: Domain Selection

Stage 1 gives the LLM only the top-level domains.

Prompt inputs:

- Filename
- Extension
- Content sample
- Top-level domain list

The LLM must return the fixed line protocol:

```text
一级域: 图书资料
二级类: 综合图书
三级类: 综合书籍
是否兜底: 是
置信度: 0.78
依据: 文件名和正文更像图书资料，但阶段一只确定一级域。
```

Only `一级域` is authoritative in stage 1. The remaining path fields are parsed for consistency but ignored for final leaf selection.

If stage 1 output is invalid, retry once with a stricter prompt. If it is still invalid, choose a deterministic domain by lightweight filename and extension heuristics. If no signal is available, use `图书资料` for book-like file patterns and `办公文档` for general office file patterns.

### Stage 2: Leaf Selection Inside Domain

Stage 2 gives the LLM only the selected domain's legal third-level paths.

Prompt inputs:

- Filename
- Extension
- Content sample
- Selected top-level domain
- All legal paths under that domain

The LLM must return the same fixed line protocol:

```text
一级域: 图书资料
二级类: 计算机图书
三级类: 编程语言书籍
是否兜底: 否
置信度: 0.91
依据: 文件名包含 Rust 编程，正文包含所有权、借用、示例代码和章节结构。
```

Backend validation rules:

- `一级域`、`二级类`、`三级类` must all exist.
- The full path must exactly match a taxonomy leaf.
- The model may return either slash-separated path or the line protocol, but the normalized path must match a legal leaf.
- The model may not create category names.
- If output is invalid, retry once.
- If retry fails, return the selected domain's fallback leaf.

## Expected Sample Outcomes

The following current misclassification examples should become regression tests:

- `Rust编程：入门、实战与进阶.pdf` -> `图书资料 / 计算机图书 / 编程语言书籍`
- `操作系统导论.pdf` -> `图书资料 / 计算机图书 / 计算机基础教材`
- `NVIDIA_CUDA_Programming_Guide_1.1_chs.pdf` -> `图书资料 / 计算机图书 / 编程语言书籍` or `研发技术 / 开发规范 / 开发手册`, depending on content sample; it must not become `架构设计` unless the sample is truly architectural.
- `浪潮之巅完整版.pdf` -> `图书资料 / 科技产业图书 / 互联网产业书籍`
- `中国是部金融史-透过金融读懂中国三千年.pdf` -> `图书资料 / 经济金融图书 / 金融历史书籍`
- `《当代中国社会分层》李强.pdf` -> `图书资料 / 社科图书 / 社会学书籍`
- `重构：改善既有代码的设计（第2版）.pdf` -> `图书资料 / 计算机图书 / 软件工程书籍`
- `modern-cpp-tutorial-zh-cn.pdf` -> `图书资料 / 计算机图书 / 编程语言书籍`

## Persistence Contract

The existing document classification fields should remain the primary storage contract:

- `classification_id`
- `classification_leaf_id`
- `classification_result`
- `classification_path`
- `classification_domain`
- `classification_score`
- `classification_confidence`
- `classification_source`
- `classification_candidates`
- `classification_review_status`
- `classification_issue_code`
- `taxonomy_version`

For `taxonomy_v3` normal results:

- `taxonomy_version` must be `taxonomy_v3`.
- `classification_result` must be the third-level leaf label.
- `classification_path` must contain exactly three path components.
- `classification_domain` must equal the first path component.
- `classification_review_status` should be `accepted`.
- `classification_issue_code` should be `None`.
- `classification_source` should be `llm_hierarchical` or `llm_hierarchical_fallback`.

Recommended extra fields:

- `classification_is_fallback`: boolean.
- `classification_reason`: short model explanation, truncated before persistence.
- `classification_model`: model identifier used for classification.

These fields are additive. If migration risk is high, they can be delayed while encoding fallback status in `classification_source`.

## Frontend Display Contract

`/documents` should separate classification from ingestion/indexing errors.

Classification column:

- Show real taxonomy path, for example `图书资料 > 计算机图书 > 编程语言书籍`.
- If `classification_source=llm_hierarchical_fallback` or `classification_is_fallback=true`, show a `兜底分类` badge.
- Do not show `未分类` or `待复核` for valid `taxonomy_v3` assignments.

Status or detail area:

- Show `RetryError[...]`, `Unsupported file type`, LightRAG errors, and local index errors outside the classification column.
- If local preview and classification are available, stale local index errors must not make the classification look broken.

Special cases:

- `.xlsx` and `.webp` files may be classified from filename and extension if content extraction is limited.
- Whitespace-only scanned documents should keep processing error detail, but classification should still try filename-driven fallback when filename has signal.
- LightRAG and embedding failures must not erase a successfully persisted classification result.

## Batch Reclassification

Existing documents should not be automatically reclassified on application startup.

Add an explicit batch reclassification entry point that supports:

- Reclassify all current `no_match` or `pending_local_content` documents.
- Reclassify selected document IDs.
- Reclassify by filters such as file type, date range, old taxonomy version, or current classification source.
- Preserve old classification snapshots for audit and rollback.

The first implementation can run synchronously in tests and expose a backend service method. A later iteration can add a UI button or admin API for long-running background jobs.

## Failure Handling

The classifier should avoid normal `no_match` output:

- Stage 1 invalid output: retry once, then deterministic domain fallback.
- Stage 2 invalid output: retry once, then selected domain fallback leaf.
- LLM transport failure: deterministic fallback leaf based on filename and extension signal.
- Empty content but informative filename: classify using filename and extension.
- Empty content and uninformative filename: persist a real fallback leaf with low confidence and keep processing error detail separately.

`classification_issue_code=no_match` should remain only as a legacy value for old records and migration filters. New `taxonomy_v3` classifications should not write it as a normal outcome.

## Test Plan

Backend tests:

- Taxonomy catalog contract: all paths are exactly three levels, IDs are unique, paths are unique, each top-level domain has exactly one fallback leaf.
- LLM parser contract: line protocol parses correctly and rejects unknown categories.
- Stage 1 domain selection: valid domain is accepted; invalid output retries and then falls back deterministically.
- Stage 2 leaf selection: valid leaf path is accepted; invalid leaf falls back to domain fallback.
- Regression examples: the listed books and tutorials route into `图书资料` or an appropriate non-office domain.
- Persistence: `taxonomy_version=taxonomy_v3`, path has three levels, `classification_issue_code` is not `no_match` for normal results.
- Batch reclassification: legacy `no_match` records can be overwritten with `taxonomy_v3` assignments without losing old snapshot data.

Frontend tests:

- `FileList` displays real three-level taxonomy paths.
- Fallback classification shows a `兜底分类` badge.
- `未分类 / 待复核` is not shown for `taxonomy_v3` accepted or fallback assignments.
- Ingest and local index errors are not rendered as classification text.

## Out Of Scope

- Rebuilding LightRAG ingestion stability.
- Automatically reclassifying the full corpus on startup.
- Replacing document extraction logic.
- Implementing embedding-based taxonomy retrieval in the first version.
- Removing legacy taxonomy fields or old `no_match` records before explicit migration.

## Implementation Notes

The recommended implementation sequence is:

1. Add `taxonomy_v3` catalog module and contract tests.
2. Add fixed-format LLM output parser tests and implementation.
3. Implement two-stage classifier behind `TaxonomyClassifier`.
4. Wire `ClassificationService` persistence to store `taxonomy_v3` assignments.
5. Add batch reclassification service method and tests.
6. Update `/documents` classification display and error separation.
7. Run focused backend and frontend regression tests.
