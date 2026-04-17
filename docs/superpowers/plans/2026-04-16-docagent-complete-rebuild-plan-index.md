# DocAgent Complete Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the complete DocAgent rebuild as four ordered, independently verifiable implementation plans that together deliver the approved architecture, LLM-heavy core chains, v2 API surface, and upgraded frontend experience.

**Architecture:** Use a staged migration. First stabilize foundation concerns shared by every later task. Then replace the ingest core, then the retrieval/QA/graph backend, then the frontend experience. Each stage leaves the system runnable and produces explicit tests or smoke checks before the next stage begins.

**Tech Stack:** FastAPI, Pydantic Settings, Alembic, SQLite, Chroma, BM25, Vue 3, Element Plus, pytest, Vitest

---

## Plan Set

### 1. Foundation

File: `docs/superpowers/plans/2026-04-16-docagent-rebuild-foundation.md`

Delivers:

- settings-driven configuration
- `/api/v2` router scaffold
- Alembic baseline
- LLM gateway
- metadata/graph persistence foundation
- delete route fix

### 2. Ingest And Classification

File: `docs/superpowers/plans/2026-04-16-docagent-rebuild-ingest-and-classification.md`

Delivers:

- normalized extraction package
- Excel/PPT block support
- chunking/indexing modules
- `IngestPipeline`
- topic service and classification feedback
- duplicate-ready ingest metadata

### 3. Retrieval QA Graph Backend

File: `docs/superpowers/plans/2026-04-16-docagent-rebuild-retrieval-qa-graph.md`

Delivers:

- query analyzer
- RRF fusion and reranker
- v2 retrieval service and APIs
- QA service and SSE route
- summary/export services
- graph and admin token-usage APIs

### 4. Frontend Experience

File: `docs/superpowers/plans/2026-04-16-docagent-rebuild-frontend-experience.md`

Delivers:

- v2 frontend API client
- QAPage and GraphPage
- query analysis and QA-aware search UI
- summary/duplicate-aware documents UI
- dashboard token-usage panel

## Execution Order

- [ ] Finish plan 1 and pass its verification steps before starting plan 2.
- [ ] Finish plan 2 and pass its verification steps before starting plan 3.
- [ ] Finish plan 3 and pass its verification steps before starting plan 4.
- [ ] After plan 4, run the combined backend and frontend verification commands from all four plans.

## Shared Constraints

- [ ] Do not revert unrelated dirty-worktree changes already present in the repository.
- [ ] Use `app/domain` as the source of truth for all new core logic.
- [ ] Keep `/api/v1` functional until `/api/v2` replacements are verified.
- [ ] Use Alembic for schema changes instead of startup-time ad hoc `ALTER TABLE` behavior.
- [ ] Preserve document-centric responses and citation traceability throughout the migration.

## Combined Verification Checklist

- [ ] Backend foundation verification from `2026-04-16-docagent-rebuild-foundation.md`
- [ ] Backend ingest verification from `2026-04-16-docagent-rebuild-ingest-and-classification.md`
- [ ] Backend retrieval/QA/graph verification from `2026-04-16-docagent-rebuild-retrieval-qa-graph.md`
- [ ] Frontend verification from `2026-04-16-docagent-rebuild-frontend-experience.md`
- [ ] One manual end-to-end smoke run:

```text
upload PDF/DOCX/XLSX/PPTX
confirm ingest_status, llm_summary, entities, and triples exist
search through /api/v2/retrieval/search and /search
ask a question through /api/v2/qa/stream and /qa
open /graph and verify node filtering
open /documents and verify duplicate + summary UI
open / and verify token-usage demo card
```
