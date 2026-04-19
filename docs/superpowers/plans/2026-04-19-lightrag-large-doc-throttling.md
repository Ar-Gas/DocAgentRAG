# LightRAG Large-Doc Throttling Implementation Plan

> This plan was revised after validating that direct edits under
> `backend/.venv/lib/python3.12/site-packages` cannot be committed reliably.
> The accepted implementation path is a repository-local runtime shim.

## Goal

Make LightRAG automatically use a larger chunk profile for large documents and
enforce document-local LLM extraction throttling so long PDFs stop overwhelming
the extraction pipeline.

## Implementation Strategy

Use a repository-local startup shim instead of modifying installed package files.

- `backend/scripts/run_lightrag_server.py` applies the patch and then delegates to
  the official LightRAG server entrypoint.
- `backend/app/services/lightrag_runtime_patch.py` monkeypatches each `LightRAG`
  instance after construction.
- `backend/app/services/lightrag_dev_config.py` emits the large-document tuning
  defaults into `backend/lightrag.env`.

This keeps the change commit-able and avoids losing behavior when `.venv` is
rebuilt.

## Tasks

### Task 1: Lock Dev Env Defaults

Add and verify these generated LightRAG env defaults:

```text
LARGE_DOC_THRESHOLD_CHUNKS=80
LARGE_DOC_CHUNK_SIZE=2400
LARGE_DOC_CHUNK_OVERLAP_SIZE=150
LARGE_DOC_CHUNK_MAX_ASYNC=1
```

Verification:

```bash
cd backend
../../../backend/.venv/bin/python -m pytest test/test_lightrag_dev_config.py -q
```

### Task 2: Add Runtime Patch Helpers

Implement large-document helpers in `backend/app/services/lightrag_runtime_patch.py`:

- build a `large_doc_profile` from estimated chunk count
- merge that profile into `doc_status.metadata`
- preserve profile metadata when LightRAG rewrites processing timestamps
- wrap chunking so large documents use larger chunk/overlap settings
- inject `large_doc_profile` into chunk payloads
- derive document-local extraction config from chunk profile

Verification:

```bash
cd backend
../../../backend/.venv/bin/python -m pytest test/test_lightrag_large_doc_runtime.py -q
```

### Task 3: Patch LightRAG Instances

Patch each `LightRAG` instance at construction time:

- wrap `chunking_func`
- patch `doc_status.upsert`
- patch `_process_extract_entities` to pass the document-local
  `llm_model_max_async` into upstream `extract_entities()`

Verification:

```bash
cd backend
../../../backend/.venv/bin/python -m pytest test/test_lightrag_server_runtime_patch.py -q
```

### Task 4: Add Startup Shim

Create `backend/scripts/run_lightrag_server.py`.

The runtime startup order must be:

1. apply `lightrag_runtime_patch.apply_runtime_patch()`
2. call the official `lightrag.api.lightrag_server.main()`

Verification:

```bash
cd backend
../../../backend/.venv/bin/python -m pytest test/test_run_lightrag_server.py -q
```

### Task 5: Runtime Rollout

Regenerate `backend/lightrag.env` if config changed, then start `9621` through
the repo shim:

```bash
cd backend
set -a
. ./lightrag.env
set +a
./.venv/bin/python scripts/run_lightrag_server.py
```

Do not use bare `./.venv/bin/lightrag-server` for this feature, because that
bypasses the repo-local runtime patch.

Runtime verification:

```bash
curl -s http://127.0.0.1:9621/health
curl -s http://127.0.0.1:6008/health
curl -s -X POST http://127.0.0.1:6008/api/v1/admin/lightrag/app/documents/reprocess_failed
```

## Acceptance Criteria

- Large documents receive `metadata.large_doc_profile`.
- Large documents use larger chunk size and overlap during chunking.
- Large document chunks carry `large_doc_profile`.
- Entity extraction receives the document-local `llm_model_max_async`.
- Existing LightRAG HTTP API and DocAgentRAG proxy paths remain unchanged.
- Targeted backend tests pass.
