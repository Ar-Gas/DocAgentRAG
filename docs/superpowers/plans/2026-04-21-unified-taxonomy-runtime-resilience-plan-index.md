# Unified Taxonomy And Runtime Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the approved unified taxonomy and runtime resilience design as two ordered implementation plans that reduce `未分类 / 待复核`, preserve frontend compatibility, and harden the LightRAG-centered document pipeline.

**Architecture:** Roll out `taxonomy_v2` first without breaking the current document DTOs, then harden runtime behavior with stage-state persistence, readiness-aware health checks, and stage-specific recovery. Keep LightRAG as the core semantic dependency, but stop letting LightRAG failures erase successful upstream work.

**Tech Stack:** FastAPI, sqlite3, pytest, Vue 3, Vitest, LightRAG, httpx

---

## Plan Set

### 1. Unified Taxonomy Classification Migration

File: `docs/superpowers/plans/2026-04-21-unified-taxonomy-classification-migration.md`

Delivers:

- `taxonomy_v2` storage fields and migration support
- a broader hierarchical taxonomy catalog with stable leaf ids
- modular classifier helpers for input building, domain routing, candidate resolution, label selection, and review policy
- compatibility mapping from legacy classifications to v2 leaf ids
- stable frontend `/documents` display with new fallback labels and minimal UI churn

### 2. Runtime Stage And Resilience Hardening

File: `docs/superpowers/plans/2026-04-21-runtime-stage-and-resilience-hardening.md`

Delivers:

- persisted per-document stage state
- readiness-aware local embedding and LightRAG runtime health
- stage-aware document service behavior that preserves partial success
- large-document and dependency-degraded RAG guardrails
- admin endpoints for runtime health and stage-specific retry

## Execution Order

- [ ] Finish plan 1 and pass its verification steps before starting plan 2.
- [ ] Do not switch default classification writes to `taxonomy_v2` until plan 1 verification passes.
- [ ] Do not wire new runtime health or retry endpoints into the admin UI until plan 2 verification passes.
- [ ] After both plans, run the combined backend and frontend verification commands listed below.

## Shared Constraints

- [ ] Do not revert unrelated dirty-worktree changes already present in the repository.
- [ ] Keep LightRAG as the long-term core dependency for semantic ingest and retrieval.
- [ ] Keep `/documents` page rendering stable by continuing to return `classification_path`, `classification_label`, `classification_review_status`, and current ingest/local index fields.
- [ ] Keep raw `no_match` reserved for abnormal inputs such as empty or unreadable content.
- [ ] Treat formal fallback labels as real taxonomy leaves, not workflow errors.
- [ ] Preserve current backend API behavior unless a task explicitly adds optional fields.
- [ ] Prefer additive migrations and compatibility shims over in-place destructive replacement.

## Combined Verification Checklist

- [ ] Backend classification verification from `2026-04-21-unified-taxonomy-classification-migration.md`
- [ ] Backend runtime verification from `2026-04-21-runtime-stage-and-resilience-hardening.md`
- [ ] Frontend `/documents` verification from `2026-04-21-unified-taxonomy-classification-migration.md`
- [ ] Manual smoke run:

```text
1. Start backend, frontend, local embedding, and LightRAG.
2. Upload a technical PDF, a DOCX office file, a scanned PDF, and a book-like PDF.
3. Confirm new uploads store taxonomy_v2 metadata without breaking current list rendering.
4. Confirm valid weak-signal documents land on formal fallback labels instead of raw no_match.
5. Force local embedding readiness failure and confirm rag_ingest is isolated without erasing local preview or classification results.
6. Retry the failed rag_ingest stage from the runtime admin endpoint and confirm recovery works after dependency readiness returns.
```
