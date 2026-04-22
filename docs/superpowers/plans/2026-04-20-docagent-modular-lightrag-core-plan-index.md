# DocAgent Modular LightRAG-Core Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the approved modular LightRAG-core architecture as five ordered implementation plans that preserve current functionality while replacing the unstable mixed architecture with a module-oriented backend and a v2-ready frontend.

**Architecture:** Use a staged migration. Start by stabilizing bootstrap, dependency boundaries, and adapter contracts. Then move document and ingest state into explicit modules and persisted jobs. After that, rebuild retrieval, QA, graph, classification, and runtime on top of the LightRAG gateway. Finish by switching the frontend onto normalized v2 APIs while keeping `/api/v1` available until verification passes.

**Tech Stack:** FastAPI, Vue 3, SQLite, LightRAG, httpx, Alembic, pytest, Vitest

---

## Plan Set

### 1. Foundation And Platform

File: `docs/superpowers/plans/2026-04-20-docagent-modular-foundation-and-platform.md`

Delivers:

- `app/bootstrap/*` application factory and settings
- `app/platform/*` shared primitives
- `app/adapters/lightrag/*` stable LightRAG gateway
- `app/adapters/legacy/*` quarantine boundary for `utils/*`
- `worker.py` scaffold
- `/api/v2` root router shell

### 2. Documents And Ingest

File: `docs/superpowers/plans/2026-04-20-docagent-modular-documents-and-ingest.md`

Delivers:

- explicit `documents`, `document_versions`, `ingest_jobs`, `lightrag_documents` persistence
- `documents` and `ingest` modules
- lifecycle and job state machines
- LightRAG-backed ingest workflow
- compatibility wiring for current upload/list/detail/delete flows

### 3. Retrieval QA Graph

File: `docs/superpowers/plans/2026-04-20-docagent-modular-retrieval-qa-graph.md`

Delivers:

- `retrieval`, `qa`, and `graph` modules
- LightRAG recall through gateway
- local citation resolution and document/block anchors
- v2 search, QA, and graph endpoints
- compatibility shims for current retrieval and QA behavior

### 4. Classification And Runtime

File: `docs/superpowers/plans/2026-04-20-docagent-modular-classification-and-runtime.md`

Delivers:

- `classification` and `runtime` modules
- version-bound classification persistence
- health, audit, repair, and dependency APIs
- removal of heavy startup reconciliation from `main.py`
- compatibility shims for current classification and admin flows

### 5. Frontend V2 Adoption

File: `docs/superpowers/plans/2026-04-20-docagent-modular-frontend-v2-adoption.md`

Delivers:

- normalized frontend API client split by domain
- adoption of v2 document, retrieval, QA, graph, classification, and runtime contracts
- degraded-state and citation-aware UI handling
- dual-stack v1/v2 toggle for safe rollout

## Execution Order

- [ ] Finish plan 1 and pass its verification steps before starting plan 2.
- [ ] Finish plan 2 and pass its verification steps before starting plan 3.
- [ ] Finish plan 3 and pass its verification steps before starting plan 4.
- [ ] Finish plan 4 and pass its verification steps before starting plan 5.
- [ ] After plan 5, run the combined backend and frontend verification commands from all five plans.

## Shared Constraints

- [ ] Do not revert unrelated dirty-worktree changes already present in the repository.
- [ ] Treat LightRAG as a required core dependency for ingest, retrieval, QA, and graph features.
- [ ] Keep SQLite as the single business control-plane source of truth.
- [ ] Keep `/api/v1` functional until `/api/v2` adoption is verified end to end.
- [ ] Route all new LightRAG access through `app/adapters/lightrag/gateway.py`.
- [ ] Route all remaining `utils/*` access through `app/adapters/legacy/*` once plan 1 lands.
- [ ] Keep long-running jobs out of the FastAPI request process once the worker scaffold is introduced.
- [ ] Add module-local README files documenting public entry points and dependency rules for every new module.

## Combined Verification Checklist

- [ ] Backend foundation verification from `2026-04-20-docagent-modular-foundation-and-platform.md`
- [ ] Documents and ingest verification from `2026-04-20-docagent-modular-documents-and-ingest.md`
- [ ] Retrieval, QA, and graph verification from `2026-04-20-docagent-modular-retrieval-qa-graph.md`
- [ ] Classification and runtime verification from `2026-04-20-docagent-modular-classification-and-runtime.md`
- [ ] Frontend verification from `2026-04-20-docagent-modular-frontend-v2-adoption.md`
- [ ] Manual end-to-end smoke run:

```text
1. Start api, worker, LightRAG, and local embedding runtime.
2. Upload sample PDF, DOCX, XLSX, and PPTX files.
3. Confirm document lifecycle reaches ready or explicit degraded state.
4. Confirm LightRAG sync status and local citation blocks exist.
5. Search through v1 and v2 retrieval endpoints.
6. Ask a question through v2 QA streaming and confirm citations open the right document blocks.
7. Open graph view and confirm node/edge payloads load for a synced document set.
8. Classify a document, review the saved result, and confirm runtime health and audit endpoints reflect the operation.
9. Use the frontend in v2 mode and confirm documents, search, QA, graph, and runtime pages all function.
```
