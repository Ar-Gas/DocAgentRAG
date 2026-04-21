# Unified Document Taxonomy And Runtime Resilience Design

## Context

The current document pipeline works, but its robustness is limited by two structural problems that amplify each other:

1. document classification is still anchored to a narrow, office-centric taxonomy that does not cover the real document mix in the system
2. document processing state collapses multiple independent failures into a single ingest outcome, which makes diagnosis and recovery coarse and unreliable

Observed issues in the current codebase and runtime:

- the `/documents` page displays `未分类` when `classification_issue_code` is `pending_local_content` or `no_match`
- `no_match` also drives the `待复核` badge even when the document is otherwise valid and readable
- the current taxonomy is too narrow for books, technical manuals, research material, scanned archives, and mixed office content
- large files are more likely to fail because successful classification and failed LightRAG ingest are not separated cleanly in the lifecycle model
- local embedding health checks currently prove process liveness but not actual model readiness
- retry behavior and failure visibility are not stage-aware, so transient infrastructure problems are mixed with business-level classification uncertainty

This design introduces a unified hierarchical taxonomy and a stage-based runtime model while keeping LightRAG as a long-term core dependency.

## Goals

1. Replace the current narrow taxonomy with a single general-purpose hierarchical taxonomy that can classify most real documents into formal labels.
2. Preserve the existing frontend contract as much as possible by continuing to expose stable `classification_path`, `classification_label`, and review fields.
3. Make `未分类 / 待复核` rare abnormal outcomes instead of normal outcomes for valid documents.
4. Keep LightRAG as the long-term core dependency for semantic ingest, retrieval, QA, and graph capabilities.
5. Separate extraction, classification, preview, and RAG ingest into independently observable and retryable runtime stages.
6. Improve large-document robustness without forcing a large rewrite of current user-facing behavior.
7. Establish module boundaries that are explicit enough for future AI-assisted changes to remain local and safe.

## Non-Goals

1. Replacing LightRAG with another retrieval engine.
2. Rewriting the frontend information architecture in the same effort.
3. Solving all parser, OCR, or file-format support gaps in one pass.
4. Eliminating every possible fallback classification outcome.
5. Migrating the entire codebase to microservices.

## Design Principles

### 1. One Unified Taxonomy

The system should have one authoritative taxonomy, not separate unrelated trees for office documents, books, and technical material.

The taxonomy should cover common real-world documents broadly enough that most valid inputs can land on a formal label. Office documents may be modeled in finer detail than other domains, but they must still live inside the same taxonomy.

### 2. Hierarchical, Stable, And Explainable Labels

Classification must remain hierarchical and path-based because the existing data model and frontend already work well with path display.

Each label should have:

- a stable machine `leaf_id`
- a display `label`
- a full `path`
- aliases
- keywords
- negative keywords
- file type hints
- an owning top-level domain

Display wording may evolve, but machine identifiers should remain stable.

### 3. Fallback Labels Are Formal Labels, Not Missing Data

For most valid documents, the system should assign a formal fallback leaf inside a real domain instead of raw `no_match`.

Examples:

- `办公文档 > 综合办公 > 通用办公材料`
- `技术文档 > 通用技术资料 > 通用技术文档`
- `图书资料 > 综合图书 > 综合书籍`

Raw `no_match` should remain reserved for genuinely abnormal inputs such as:

- empty or whitespace-only content
- unreadable corrupted files
- extraction output that is too weak to classify
- OCR or parser output that is mostly noise

### 4. Stage State Is The Source Of Operational Truth

The document pipeline should model each processing stage independently. A final aggregate status may still be returned to the frontend, but it must be derived from stage state instead of hiding it.

### 5. LightRAG Is Core But Not The Only Runtime Concern

LightRAG remains a mandatory dependency for semantic knowledge operations, but the application must not collapse all document handling into LightRAG success or failure. Classification, preview, and local metadata should keep working even when RAG ingest is degraded.

## Target Taxonomy Shape

## Top-Level Domains

The top level should stay small and stable. Recommended initial range is `12-18` domains.

Recommended domains:

- `办公文档`
- `技术文档`
- `图书资料`
- `研究分析`
- `财务与审计`
- `法务与合规`
- `人力与组织`
- `运营与服务`
- `产品与项目`
- `市场与销售`
- `数据与智能`
- `采购与供应链`
- `战略与经营`
- `培训与知识库`
- `档案与证照`
- `通用综合`

These domains are intentionally broad. The goal is routing stability, not a perfect semantic ontology.

## Hierarchy Depth

Use a three-level structure:

1. level one: domain
2. level two: scenario or theme cluster
3. level three: stable leaf label

Example paths:

- `办公文档 > 汇报材料 > 工作汇报`
- `办公文档 > 制度流程 > 管理制度`
- `技术文档 > 软件工程 > 架构设计`
- `技术文档 > 运维体系 > 运维手册`
- `图书资料 > 计算机图书 > 编程语言书籍`
- `研究分析 > 行业研究 > 行业报告`

The system should avoid deeper trees unless there is a proven need. Overly deep taxonomies increase drift and reduce classification stability.

## Recommended Label Volume

Recommended rollout target:

- phase one: `150-250` leaf labels
- phase two: `250-400` leaf labels if production data shows consistent need

This is broad enough to reduce fallback frequency without turning the taxonomy into a brittle ontology project.

## Label Authoring Rules

Every leaf label should follow these rules:

1. the label is a stable noun phrase, not a workflow state
2. the label is usable across document sources and not tied to one department unless necessary
3. the label belongs to exactly one primary path
4. aliases may be many, but canonical path is one
5. file type hints guide scoring but do not decide the result alone
6. every major domain has a small number of formal fallback leaves

Examples of good leaf labels:

- `会议纪要`
- `项目方案`
- `测试文档`
- `架构设计`
- `产品需求`
- `技术手册`
- `行业报告`
- `学术资料`
- `综合书籍`

Examples of bad leaf labels:

- `待整理`
- `未知文件`
- `其他`
- `刚上传`
- `需要复核`

Operational states belong to workflow state, not taxonomy.

## Taxonomy Metadata Model

Each taxonomy leaf should include:

- `leaf_id`
- `path`
- `domain`
- `label`
- `aliases`
- `keywords`
- `negative_keywords`
- `file_types`
- `fallback_rank`
- `enabled`
- `taxonomy_version`

Optional future fields:

- `language_hints`
- `content_patterns`
- `priority_boost_rules`
- `example_titles`

The taxonomy definition should be loaded from a dedicated module or structured data source, not embedded as scattered hard-coded lists across service code.

## Classification Architecture

## Target Module Split

The current classifier should evolve into a small orchestration layer backed by focused submodules.

Recommended module split:

- `classification_input_builder.py`
- `taxonomy_domain_router.py`
- `taxonomy_candidate_resolver.py`
- `taxonomy_label_selector.py`
- `taxonomy_review_policy.py`
- `taxonomy_classifier.py`

Responsibilities:

- `classification_input_builder.py`
  - build normalized title, file name, extension, extracted text summary, and content heuristics
- `taxonomy_domain_router.py`
  - select top-level domain candidates
- `taxonomy_candidate_resolver.py`
  - gather valid leaf candidates inside the selected domain
- `taxonomy_label_selector.py`
  - select one leaf label from constrained candidates
- `taxonomy_review_policy.py`
  - decide whether result is accepted, downgraded to domain fallback, or marked abnormal
- `taxonomy_classifier.py`
  - orchestrate the flow and return the stable output contract

This split keeps classification behavior editable without turning one file into the only place where routing, candidate recall, label choice, and review logic all mix together.

## Classification Decision Flow

Recommended flow:

1. build a normalized classification input package
2. route to one or more top-level domain candidates
3. resolve in-domain candidate leaves using metadata and content hints
4. select the best leaf among constrained candidates
5. if confidence is weak but the domain is clear, downgrade to a formal domain fallback leaf
6. only emit raw `no_match` when the content is truly abnormal or insufficient

This flow changes `no_match` from a normal classification outcome into an exceptional workflow outcome.

## Output Contract

The classification service should continue returning a stable normalized result with:

- `classification_leaf_id`
- `classification_label`
- `classification_path`
- `classification_domain`
- `classification_review_status`
- `classification_issue_code`
- `classification_confidence`
- `taxonomy_version`

The frontend may continue to rely mainly on `classification_path`, `classification_label`, and `classification_review_status`.

## Migration And Compatibility

## Dual-Version Taxonomy

Migration should use two explicit taxonomy versions:

- `taxonomy_v1`
- `taxonomy_v2`

The business response model stays stable while internal storage learns to track taxonomy version and canonical leaf identity.

Recommended new internal fields:

- `taxonomy_version`
- `classification_leaf_id`
- `classification_domain`
- `classification_confidence`

The existing display fields remain:

- `classification_label`
- `classification_path`
- `classification_review_status`
- `classification_issue_code`

## Compatibility Adapter

All taxonomy compatibility behavior should be centralized in a dedicated adapter, not spread across service and API code.

Recommended responsibility:

- map old `classification_id` or old path segments to new canonical leaf identities when possible
- normalize old and new classification records to one output DTO
- isolate version-specific branching from the rest of the codebase

Recommended internal component:

- `taxonomy_migration_map`

This map should support:

- direct one-to-one mappings
- explicit `requires_reclassification`
- alias support for historical labels

## Historical Data Strategy

Historical documents should be split into three groups:

1. documents with old labels that map cleanly to `v2`
2. documents with `no_match`, `needs_review`, or `pending_local_content`
3. documents whose ingest failed because downstream runtime dependencies failed

Recommended treatment:

- group one: metadata migration only
- group two: re-run classification in `v2`
- group three: fix runtime stability first, then backfill classification and RAG stages separately

This prevents classification migration from being blocked by runtime infrastructure issues.

## Frontend Compatibility

The frontend should not need to understand taxonomy versioning.

The backend should continue returning one standardized display DTO. For old documents, the backend adapts the stored data into the normalized output contract. For new documents, the backend returns `v2` data directly.

This keeps pages such as `/documents` stable while the backend migrates gradually.

## Runtime Architecture

## Stage Model

Document processing should be decomposed into explicit stages:

- `content_extract`
- `content_normalize`
- `taxonomy_classify`
- `local_preview_index`
- `rag_ingest`
- `post_check`

Each stage should track:

- `status`
- `error_code`
- `error_message`
- `retry_count`
- `started_at`
- `updated_at`

This stage state becomes the authoritative operational truth.

## Aggregate Document State

The user-facing status may remain simple, but it should be derived from stage state.

Examples:

- classification succeeded, RAG ingest failed
- preview available, content extraction degraded
- file saved, classification pending
- RAG waiting for dependency recovery

This allows the product to expose a useful high-level view without losing diagnostic precision.

## Queue-Based Execution

Upload requests should stop trying to complete the full pipeline inline. The system should register the file and enqueue stage work for background execution.

Benefits:

- large files do not block request handling
- transient dependency errors can be retried by stage
- classification can complete even when LightRAG is degraded
- operational recovery becomes targeted instead of global

This remains a modular monolith design. It does not require external distributed orchestration.

## Health Model

Infrastructure checks should distinguish:

- `liveness`
- `readiness`
- `degraded`

For embedding and LightRAG integration:

- `liveness` means the process is alive and reachable
- `readiness` means the dependency can complete a minimal real operation
- `degraded` means the dependency is technically alive but capacity or error rate is unhealthy

RAG ingest should only run when dependencies are ready enough to do real work.

## Large Document Strategy

Large files should not use the exact same execution policy as short files.

After extraction, compute a lightweight document profile:

- file type
- page count if available
- extracted text length
- chunk estimate
- scanned or OCR-heavy indicator

Use the profile to select an execution policy:

- small documents: normal concurrency
- medium documents: lower ingest concurrency
- large documents: serialized or throttled embedding policy
- extra-large documents: complete classification and preview first, delay RAG ingest into a lower-priority queue

This prevents a few huge files from destabilizing the entire runtime.

## Retry And Failure Policy

Retry policy must be stage-specific.

Recommended policy:

- extraction failures caused by unsupported or damaged files
  - terminal business error
  - no aggressive infrastructure retry
- classification failures caused by model timeout or provider instability
  - limited short retry
- embedding or RAG failures caused by dependency connectivity
  - exponential backoff
  - shared circuit breaker
- `no_match`
  - not an infrastructure retry case
  - enter review or later reclassification workflow

This keeps operational retries aligned with actual failure type.

## Circuit Breaking And Degraded Operation

When embedding or LightRAG dependencies fail repeatedly, the system should enter a degraded runtime mode for `rag_ingest`:

- pause new RAG stage execution
- preserve uploaded documents and completed upstream stages
- keep classification, preview, and metadata storage active
- surface a clear degraded status to operators

This is safer than continuing to hammer an unhealthy dependency and producing large volumes of repeated `RetryError` failures.

## Logging And Observability

Operational visibility should be split into two layers:

1. service logs
2. document or job event logs

Recommended service log structure:

- `logs/backend/`
- `logs/lightrag/`
- `logs/local_embedding/`
- `logs/frontend/`

Recommended task-event structure:

- one event stream per `document_id` or `job_id`
- stage transitions
- retry events
- dependency health state transitions

Logs should be rotated and retained by policy instead of growing without bound.

Recommended policy:

- daily rotation
- keep recent hot logs locally
- compress older logs
- allow per-service retention tuning

## Administrative Recovery Actions

Operational controls should be stage-aware.

Recommended actions:

- retry classification
- retry RAG ingest
- re-run extraction
- batch retry transient dependency failures
- batch send old `no_match` documents into new taxonomy backfill

This is materially more useful than one generic retry button.

## Module Design For AI-Friendly Maintenance

The classification and runtime redesign should explicitly support future AI-assisted maintenance.

Required characteristics:

- each module has one clear responsibility
- public entry points are stable and narrow
- version-specific compatibility logic is isolated
- stage state and taxonomy definitions are data-driven where possible
- module-local tests validate contracts and regressions

Recommended module boundaries:

- taxonomy definition module
- classification orchestration module
- taxonomy compatibility module
- runtime stage state module
- job execution or queue module
- dependency health module
- stage retry policy module

This reduces the risk that future changes require editing unrelated files across the entire repository.

## Rollout Plan

## Phase 1: Foundation

Deliver:

- `taxonomy_v2` data model
- version fields and compatibility adapter
- stage-state schema
- structured logging and event model foundations

Do not change user-visible behavior yet beyond internal compatibility support.

## Phase 2: New Uploads On v2 Taxonomy

Deliver:

- route new uploads through `taxonomy_v2`
- keep old documents readable through the compatibility adapter
- keep the frontend on the same normalized DTO

Expected user-facing change:

- fewer new documents land in raw `未分类 / 待复核`

## Phase 3: Historical Backfill

Prioritize:

- old `no_match`
- `needs_review`
- `pending_local_content`
- cleanly mappable old labels

Run historical migration asynchronously and by priority instead of doing a full-library rewrite in one batch.

## Phase 4: Runtime Hardening

Deliver:

- large-document profiling
- staged queue execution
- readiness checks
- stage-specific retry
- RAG circuit breaker and degraded mode

Expected user-facing change:

- large files no longer fail in a way that erases successful upstream work

## Phase 5: Legacy Write-Path Reduction

After observing production stability:

- consider stopping `taxonomy_v1` writes
- simplify compatibility logic where safe
- retain read compatibility long enough for rollback confidence

## Acceptance Criteria

## Classification Outcomes

- new uploads show a materially lower `未分类 / 待复核` rate
- technical documents, office documents, and books can usually land on formal labels
- raw `no_match` is mostly limited to abnormal or unreadable content

## Compatibility Outcomes

- existing frontend display code can keep consuming `classification_path`, `classification_label`, and review fields
- old and new documents return a uniform display contract
- migration does not produce widespread blank or broken paths in `/documents`

## Runtime Outcomes

- embedding or LightRAG readiness failures no longer masquerade as generic classification or ingest ambiguity
- successful upstream stages remain preserved when downstream stages fail
- large-document handling degrades gracefully instead of collapsing the entire workflow

## Operational Outcomes

- logs and task events make it clear which stage failed
- operators can retry by stage and by error class
- degraded dependency states are visible and actionable

## Maintenance Outcomes

- taxonomy expansion can happen by editing a bounded taxonomy definition and classification modules
- future AI-assisted changes do not need to modify the frontend contract for routine taxonomy growth
- stage-based runtime changes remain local to runtime modules instead of bleeding into unrelated document APIs

## Out-Of-Scope Follow-Ups

The following are good follow-up topics but should remain outside this design unless explicitly pulled in later:

- deeper OCR quality improvements for scanned archives
- dedicated spreadsheet semantic extraction
- richer human review tooling for manual taxonomy correction
- taxonomy analytics dashboards
- multilingual classification tuning
